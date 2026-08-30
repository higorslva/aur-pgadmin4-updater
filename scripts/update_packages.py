import re
import requests
import os
from pathlib import Path
from packaging.version import parse as parse_version

PACKAGES_URL = "https://ftp.postgresql.org/pub/pgadmin/pgadmin4/apt/noble/dists/pgadmin4/main/binary-amd64/Packages"
APT_BASE_URL = PACKAGES_URL.split("dists/")[0]
PROJECT_ROOT = Path(__file__).parent.parent

PACKAGES_TO_UPDATE = {
    "pgadmin4-server": "pgadmin4-server-bin",
    "pgadmin4-desktop": "pgadmin4-desktop-bin"
}

def get_latest_versions_map():
    print(f"Downloading {PACKAGES_URL} ...")
    resp = requests.get(PACKAGES_URL)
    resp.raise_for_status()
    
    blocks = re.split(r"\n(?=Package:)", resp.text)
    latest_data = {}

    for block in blocks:
        pkg_name_match = re.search(r"Package: ([\w-]+)", block)
        ver_match = re.search(r"Version: ([\w\.\-\+~:]+)", block)
        sha_match = re.search(r"SHA256: ([a-f0-9]{64})", block)
        fn_match = re.search(r"^Filename: (.*)", block, re.M)
        
        if pkg_name_match and ver_match and sha_match and fn_match:
            name = pkg_name_match.group(1)
            version = ver_match.group(1)
            sha = sha_match.group(1)
            filename = fn_match.group(1)
            
            if name in PACKAGES_TO_UPDATE:
                # If multiple versions exist in the file, keep the highest one
                if name not in latest_data or parse_version(version) > parse_version(latest_data[name][0]):
                    latest_data[name] = (version, sha, filename)
    
    return latest_data

def sanitize_pkgver(version):
    # Strip the Debian revision, e.g. 9.17-1 -> 9.17
    return version.split("-")[0]

SOURCE_URL_PATTERN = re.compile(
    r"https://ftp\.postgresql\.org/pub/pgadmin/pgadmin4/apt/noble/dists/pgadmin4/main/binary-amd64/"
    r"pgadmin4-(?:server|desktop)_[^\s\"')]*\.deb"
)

def update_pkgbuild(package_dir, new_ver, new_sha, new_filename):
    pkgbuild_path = PROJECT_ROOT / package_dir / "PKGBUILD"
    if not pkgbuild_path.exists():
        print(f"Warning: {pkgbuild_path} not found.")
        return False

    pkgver = sanitize_pkgver(new_ver)
    new_url = APT_BASE_URL + new_filename
    content = pkgbuild_path.read_text()

    # Comparison
    current_ver = re.search(r"^pkgver=([^\n]+)", content, re.M).group(1)
    current_sha = re.search(r"^sha256sums=\('([a-f0-9]{64})'", content, re.M).group(1)
    current_url = None
    for line in content.splitlines():
        if not line.lstrip().startswith("#") and "binary-amd64/pgadmin4-" in line:
            current_url = SOURCE_URL_PATTERN.search(line)
            if current_url:
                current_url = current_url.group(0)
                break
    # Resolve the ${pkgver} template in the source URL against the current version
    resolved_url = current_url.replace("${pkgver}", current_ver) if current_url else None

    if current_ver == pkgver and current_sha == new_sha and resolved_url == new_url:
        print(f"[{package_dir}] Already up to date ({pkgver}).")
        return False

    changes = []
    if current_ver != pkgver:
        content = re.sub(r"^pkgver=.*$", f"pkgver={pkgver}", content, flags=re.M)
        changes.append("pkgver")

    if current_sha != new_sha:
        content = re.sub(r"(^sha256sums=\(')[a-f0-9]{64}(')", f"\\g<1>{new_sha}\\g<2>", content, flags=re.M)
        changes.append("sha256sums")

    if current_url is not None and resolved_url != new_url:
        new_lines = []
        for line in content.splitlines(keepends=True):
            if not line.lstrip().startswith("#") and "binary-amd64/pgadmin4-" in line:
                line = SOURCE_URL_PATTERN.sub(new_url, line)
            new_lines.append(line)
        content = "".join(new_lines)
        changes.append("source")

    if current_ver == pkgver:
        pkgrel_match = re.search(r"^pkgrel=(\d+)", content, re.M)
        if pkgrel_match:
            content = re.sub(r"^pkgrel=(\d+)", f"pkgrel={int(pkgrel_match.group(1)) + 1}", content, flags=re.M)
            changes.append("pkgrel")

    pkgbuild_path.write_text(content)
    print(f"[{package_dir}] Updated to {pkgver} ({', '.join(changes)}).")
    return True

if __name__ == "__main__":
    latest_info = get_latest_versions_map()
    updates_made = []

    for upstream_name, local_dir in PACKAGES_TO_UPDATE.items():
        if upstream_name in latest_info:
            ver, sha, filename = latest_info[upstream_name]
            if update_pkgbuild(local_dir, ver, sha, filename):
                updates_made.append(local_dir)
    
    if updates_made:
        updated_str = ','.join(updates_made)
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"updated_dirs={updated_str}\n")
        else:
            print(f"DEBUG: updated_dirs={updated_str}")
