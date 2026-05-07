# pgAdmin4 AUR Automation

Automated maintenance and synchronization for **pgAdmin4** binary packages in the **Arch User Repository (AUR)**. This repository acts as a monorepo to manage, update, and deploy both the server and desktop components of pgAdmin4.

## 📦 Packages Maintained

| Package | Description | AUR Link |
| :--- | :--- | :--- |
| **pgadmin4-server-bin** | The core server package for pgAdmin4. | [aur.archlinux.org/packages/pgadmin4-server-bin](https://aur.archlinux.org/packages/pgadmin4-server-bin) |
| **pgadmin4-desktop-bin** | The desktop user interface for pgAdmin4. | [aur.archlinux.org/packages/pgadmin4-desktop-bin](https://aur.archlinux.org/packages/pgadmin4-desktop-bin) |

---

## 🚀 How it Works

This repository uses **GitHub Actions** and a custom **Python automation script** to ensure the AUR packages are always up-to-date with the official PostgreSQL APT repository.

1.  **Daily Check:** A workflow runs every day at midnight to fetch the latest versions from the upstream repository.
2.  **Version Comparison:** The script parses the upstream `Packages` file and compares versions and SHA256 hashes with the current `PKGBUILD` files.
3.  **Auditability:** If a new version is found, the script updates the `PKGBUILD` and generates a new `.SRCINFO` using an **Arch Linux Docker container** to ensure metadata integrity.
4.  **Automated Deploy:** Changes are committed and pushed directly to the AUR via SSH using a dedicated automation key.

---

## 📁 Repository Structure

```text
pgadmin4-aur/
├── .github/workflows/
│   └── aur-sync.yml          # GitHub Actions CI/CD logic
├── pgadmin4-server-bin/
│   └── PKGBUILD              # Server package build script
├── pgadmin4-desktop-bin/
│   └── PKGBUILD              # Desktop package build script
└── scripts/
    └── update_packages.py    # Python logic for version tracking
```

---

## 🛠 Setup & Configuration

To replicate this automation in your own fork:

### 1. SSH Key
Generate a new SSH key without a passphrase for the AUR:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_aur_automation
```
Add the public key to your AUR account and the private key to GitHub Secrets as `AUR_SSH_PRIVATE_KEY`.

### 2. GitHub Secrets
Ensure the following secret is configured in your repository:
*   `AUR_SSH_PRIVATE_KEY`: The private Ed25519 key used for AUR authentication.

---

## ⚖️ License

The `PKGBUILD` files and automation scripts are provided under the **PostgreSQL License**.

**Maintainer**: Higor Silva ([@higorslva](https://github.com/higorslva)).
