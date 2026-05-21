import re
import requests
import os
from pathlib import Path
from packaging.version import parse as parse_version

PACKAGES_URL = "https://ftp.postgresql.org/pub/pgadmin/pgadmin4/apt/noble/dists/pgadmin4/main/binary-amd64/Packages"
PROJECT_ROOT = Path(__file__).parent.parent

PACKAGES_TO_UPDATE = {
    "pgadmin4-server": "pgadmin4-server-bin",
    "pgadmin4-desktop": "pgadmin4-desktop-bin"
}

def get_latest_versions_map():
    print(f"Baixando {PACKAGES_URL} ...")
    resp = requests.get(PACKAGES_URL)
    resp.raise_for_status()
    
    blocks = re.split(r"\n(?=Package:)", resp.text)
    latest_data = {}

    for block in blocks:
        pkg_name_match = re.search(r"Package: ([\w-]+)", block)
        ver_match = re.search(r"Version: ([\w\.\-\+~:]+)", block)
        sha_match = re.search(r"SHA256: ([a-f0-9]{64})", block)
        
        if pkg_name_match and ver_match and sha_match:
            name = pkg_name_match.group(1)
            version = ver_match.group(1)
            sha = sha_match.group(1)
            
            if name in PACKAGES_TO_UPDATE:
                # Se houver múltiplas versões no arquivo, mantém a maior
                if name not in latest_data or parse_version(version) > parse_version(latest_data[name][0]):
                    latest_data[name] = (version, sha)
    
    return latest_data

def update_pkgbuild(package_dir, new_ver, new_sha):
    pkgbuild_path = PROJECT_ROOT / package_dir / "PKGBUILD"
    if not pkgbuild_path.exists():
        print(f"Aviso: {pkgbuild_path} não encontrado.")
        return False

    content = pkgbuild_path.read_text()
    
    # Comparação
    current_ver = re.search(r"^pkgver=([^\n]+)", content, re.M).group(1)
    current_sha = re.search(r"^sha256sums=\('([a-f0-9]{64})'", content, re.M).group(1)

    if current_ver == new_ver and current_sha == new_sha:
        print(f"[{package_dir}] Já está na versão mais recente ({new_ver}).")
        return False

    # Atualização
    content = re.sub(r"^pkgver=.*$", f"pkgver={new_ver}", content, flags=re.M)
    content = re.sub(r"(^sha256sums=\(')[a-f0-9]{64}(')", f"\\g<1>{new_sha}\\g<2>", content, flags=re.M)
    
    pkgbuild_path.write_text(content)
    print(f"[{package_dir}] Atualizado para {new_ver}")
    return True

if __name__ == "__main__":
    latest_info = get_latest_versions_map()
    updates_made = []

    for upstream_name, local_dir in PACKAGES_TO_UPDATE.items():
        if upstream_name in latest_info:
            ver, sha = latest_info[upstream_name]
            if update_pkgbuild(local_dir, ver, sha):
                updates_made.append(local_dir)
    
    if updates_made:
        updated_str = ','.join(updates_made)
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"updated_dirs={updated_str}\n")
        else:
            print(f"DEBUG: updated_dirs={updated_str}")
