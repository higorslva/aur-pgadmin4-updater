import re
import hashlib
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

# Packages whose source pulls requirements.txt from a GitHub release tag.
# They only update to a version whose REL-x_y tag already exists upstream.
TAG_GATED = {"pgadmin4-server"}

_TAG_CACHE = {}

def get_versions_map():
    print(f"Downloading {PACKAGES_URL} ...")
    resp = requests.get(PACKAGES_URL)
    resp.raise_for_status()
    
    blocks = re.split(r"\n(?=Package:)", resp.text)
    versions_data = {}

    for block in blocks:
        pkg_name_match = re.search(r"Package: ([\w-]+)", block)
        ver_match = re.search(r"Version: ([\w\.\-\+~:]+)", block)
        sha_match = re.search(r"SHA256: ([a-f0-9]{64})", block)
        fn_match = re.search(r"^Filename: (.*)", block, re.M)
        
        if pkg_name_match and ver_match and sha_match and fn_match:
            name = pkg_name_match.group(1)
            if name in PACKAGES_TO_UPDATE:
                # Keep every version so a tag-gated package can fall back
                # to the newest release that already has a GitHub tag
                versions_data.setdefault(name, {})[ver_match.group(1)] = (sha_match.group(1), fn_match.group(1))

    versions_map = {}
    for name, entries in versions_data.items():
        ordered = sorted(entries.items(), key=lambda kv: parse_version(kv[0]), reverse=True)
        versions_map[name] = [(ver, sha, filename) for ver, (sha, filename) in ordered]

    return versions_map

def tag_exists(pkgver, token=None):
    if pkgver not in _TAG_CACHE:
        tag = "REL-" + pkgver.replace(".", "_")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(
            f"https://api.github.com/repos/pgadmin-org/pgadmin4/git/ref/tags/{tag}",
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 404:
            _TAG_CACHE[pkgver] = False
        else:
            resp.raise_for_status()
            _TAG_CACHE[pkgver] = True
    return _TAG_CACHE[pkgver]

def sanitize_pkgver(version):
    # Strip the Debian revision, e.g. 9.17-1 -> 9.17
    return version.split("-")[0]

SOURCE_URL_PATTERN = re.compile(
    r"https://ftp\.postgresql\.org/pub/pgadmin/pgadmin4/apt/noble/dists/pgadmin4/main/binary-amd64/"
    r"pgadmin4-(?:server|desktop)_[^\s\"')]*\.deb"
)

def _sha256sums_block(content):
    m = re.search(r"sha256sums=\((.*?)\)", content, re.DOTALL)
    return m.group(1) if m else None

def _read_first_sha(content):
    block = _sha256sums_block(content)
    if not block:
        return None
    m = re.search(r"[a-f0-9]{64}", block)
    return m.group(0) if m else None

def _replace_first_sha(content, new_sha):
    m = re.search(r"(sha256sums=\([^)]*?)[a-f0-9]{64}", content, re.DOTALL)
    if not m:
        return content
    return content[: m.end(1)] + new_sha + content[m.end(1) + 64:]

def _replace_requirements_sha(content, new_sha):
    # Replace the requirements hash (2nd entry) inside the sha256sums block,
    # or the 'SKIP' placeholder when only the .deb hash is present.
    m = re.search(r"sha256sums=\((.*?)\)", content, re.DOTALL)
    if not m:
        return content
    block_start = m.start(1)
    block = m.group(1)
    hashes = list(re.finditer(r"[a-f0-9]{64}", block))
    if len(hashes) >= 2:
        start = block_start + hashes[1].start()
        return content[:start] + new_sha + content[start + 64:]
    skip = re.search(r"'SKIP'", block)
    if skip:
        start = block_start + skip.start()
        end = block_start + skip.end()
        return content[:start] + f"'{new_sha}'" + content[end:]
    return content

def _has_requirements(content):
    return bool(re.search(r"requirements.{0,20}\.txt::https", content))

def fetch_requirements_sha(pkgver):
    tag = "REL-" + pkgver.replace(".", "_")
    url = f"https://raw.githubusercontent.com/pgadmin-org/pgadmin4/refs/tags/{tag}/requirements.txt"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        return None
    return hashlib.sha256(resp.text.encode("utf-8")).hexdigest()

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
    current_sha = _read_first_sha(content)
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
        content = _replace_first_sha(content, new_sha)
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

    if _has_requirements(content):
        requirements_sha = fetch_requirements_sha(pkgver)
        if requirements_sha is None:
            print(f"Warning: could not fetch requirements.txt for REL-{pkgver.replace('.', '_')}; keeping existing hash.")
        else:
            new_content = _replace_requirements_sha(content, requirements_sha)
            if new_content != content:
                content = new_content
                changes.append("requirements")

    pkgbuild_path.write_text(content)
    print(f"[{package_dir}] Updated to {pkgver} ({', '.join(changes)}).")
    return True

if __name__ == "__main__":
    versions_map = get_versions_map()
    token = os.environ.get("GITHUB_TOKEN")
    updates_made = []

    for upstream_name, local_dir in PACKAGES_TO_UPDATE.items():
        candidates = versions_map.get(upstream_name, [])
        if not candidates:
            print(f"[{local_dir}] No upstream versions found; skipping.")
            continue

        chosen = candidates[0]
        if upstream_name in TAG_GATED:
            # Fall back to the newest release that already has its GitHub tag
            chosen = next(
                ((ver, sha, filename) for ver, sha, filename in candidates
                 if tag_exists(sanitize_pkgver(ver), token)),
                None,
            )
            if chosen is None:
                print(f"[{local_dir}] No upstream REL tag available yet; skipping.")
                continue

        ver, sha, filename = chosen
        if update_pkgbuild(local_dir, ver, sha, filename):
            updates_made.append(local_dir)
    
    if updates_made:
        updated_str = ','.join(updates_made)
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"updated_dirs={updated_str}\n")
        else:
            print(f"DEBUG: updated_dirs={updated_str}")
