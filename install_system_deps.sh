#!/usr/bin/env bash

set -euo pipefail

REQUIRED_COMMANDS=(cmake clangd autoreconf aclocal)
CAPTURE_TOOLS=(bear intercept-build)

log() {
  echo "[install_system_deps] $*"
}

have_command() {
  command -v "$1" >/dev/null 2>&1
}

array_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

missing_commands() {
  local missing=()
  local cmd
  for cmd in "${REQUIRED_COMMANDS[@]}"; do
    if ! have_command "$cmd"; then
      missing+=("$cmd")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi
  printf '%s\n' "${missing[@]}"
}

has_capture_tool() {
  local cmd
  for cmd in "${CAPTURE_TOOLS[@]}"; do
    if have_command "$cmd"; then
      return 0
    fi
  done
  return 1
}

has_libtool_bootstrap_tool() {
  have_command libtoolize || have_command glibtoolize
}

all_missing_requirements() {
  missing_commands
  if ! has_libtool_bootstrap_tool; then
    printf '%s\n' "libtoolize/glibtoolize"
  fi
  if ! has_capture_tool; then
    printf '%s\n' "bear/intercept-build"
  fi
}

detect_linux_pkg_manager() {
  local manager
  for manager in apt-get dnf yum pacman zypper; do
    if have_command "$manager"; then
      echo "$manager"
      return
    fi
  done
  return 1
}

need_sudo() {
  [[ "$(id -u)" -ne 0 ]]
}

run_privileged() {
  if need_sudo; then
    sudo "$@"
  else
    "$@"
  fi
}

apt_package_exists() {
  apt-cache show "$1" >/dev/null 2>&1
}

choose_apt_package() {
  local candidate
  for candidate in "$@"; do
    if apt_package_exists "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

choose_linux_package() {
  local manager="$1"
  local command_name="$2"

  case "$manager" in
    apt-get)
      case "$command_name" in
        cmake) echo "cmake" ;;
        clangd) choose_apt_package clangd clangd-18 clangd-17 clangd-16 ;;
        autoreconf) echo "autoconf" ;;
        aclocal) echo "automake" ;;
        libtoolize) echo "libtool" ;;
        glibtoolize) echo "libtool" ;;
        bear) echo "bear" ;;
        intercept-build) choose_apt_package clang-tools clang-tools-18 clang-tools-17 clang-tools-16 ;;
      esac
      ;;
    dnf|yum)
      case "$command_name" in
        cmake) echo "cmake" ;;
        clangd) echo "clang-tools-extra" ;;
        autoreconf) echo "autoconf" ;;
        aclocal) echo "automake" ;;
        libtoolize|glibtoolize) echo "libtool" ;;
        bear) echo "bear" ;;
        intercept-build) echo "clang-tools-extra" ;;
      esac
      ;;
    pacman)
      case "$command_name" in
        cmake) echo "cmake" ;;
        clangd) echo "clang" ;;
        autoreconf) echo "autoconf" ;;
        aclocal) echo "automake" ;;
        libtoolize|glibtoolize) echo "libtool" ;;
        bear) echo "bear" ;;
        intercept-build) echo "clang" ;;
      esac
      ;;
    zypper)
      case "$command_name" in
        cmake) echo "cmake" ;;
        clangd) echo "clang-tools" ;;
        autoreconf) echo "autoconf" ;;
        aclocal) echo "automake" ;;
        libtoolize|glibtoolize) echo "libtool" ;;
        bear) echo "bear" ;;
        intercept-build) echo "clang-tools" ;;
      esac
      ;;
  esac
}

install_with_brew() {
  local packages=()
  local cmd

  if ! have_command brew; then
    log "Homebrew is required on macOS. Install it first from https://brew.sh/."
    exit 1
  fi

  for cmd in "${REQUIRED_COMMANDS[@]}"; do
    if have_command "$cmd"; then
      continue
    fi
    case "$cmd" in
      cmake)
        if ! array_contains "cmake" "${packages[@]-}"; then
          packages+=("cmake")
        fi
        ;;
      clangd)
        if ! array_contains "llvm" "${packages[@]-}"; then
          packages+=("llvm")
        fi
        ;;
      autoreconf)
        if ! array_contains "autoconf" "${packages[@]-}"; then
          packages+=("autoconf")
        fi
        ;;
      aclocal)
        if ! array_contains "automake" "${packages[@]-}"; then
          packages+=("automake")
        fi
        ;;
    esac
  done

  if ! has_capture_tool; then
    if ! array_contains "bear" "${packages[@]-}"; then
      packages+=("bear")
    fi
  fi

  if ! has_libtool_bootstrap_tool; then
    if ! array_contains "libtool" "${packages[@]-}"; then
      packages+=("libtool")
    fi
  fi

  if [[ ${#packages[@]} -eq 0 ]]; then
    log "All required system commands are already installed."
    return
  fi

  log "Detected macOS. Missing requirements: $(all_missing_requirements | tr '\n' ' ' | xargs)"
  brew update
  log "Installing packages: ${packages[*]}"
  brew install "${packages[@]}"
}

install_with_linux_manager() {
  local manager="$1"
  local packages=()
  local cmd
  local package_name

  for cmd in "${REQUIRED_COMMANDS[@]}"; do
    if have_command "$cmd"; then
      continue
    fi
    package_name="$(choose_linux_package "$manager" "$cmd" || true)"
    if [[ -z "$package_name" ]]; then
      log "No package mapping found for missing command '$cmd' with package manager '$manager'."
      exit 1
    fi
    if ! array_contains "$package_name" "${packages[@]-}"; then
      packages+=("$package_name")
    fi
  done

  if ! has_capture_tool; then
    package_name="$(choose_linux_package "$manager" "intercept-build" || true)"
    if [[ -z "$package_name" ]]; then
      package_name="$(choose_linux_package "$manager" "bear" || true)"
    fi
    if [[ -z "$package_name" ]]; then
      log "No package mapping found for capture tools with package manager '$manager'."
      exit 1
    fi
    if ! array_contains "$package_name" "${packages[@]-}"; then
      packages+=("$package_name")
    fi
  fi

  if ! has_libtool_bootstrap_tool; then
    package_name="$(choose_linux_package "$manager" "libtoolize" || true)"
    if [[ -z "$package_name" ]]; then
      log "No package mapping found for libtool bootstrap tools with package manager '$manager'."
      exit 1
    fi
    if ! array_contains "$package_name" "${packages[@]-}"; then
      packages+=("$package_name")
    fi
  fi

  if [[ ${#packages[@]} -eq 0 ]]; then
    log "All required system commands are already installed."
    return
  fi

  log "Detected Linux with package manager '$manager'. Missing requirements: $(all_missing_requirements | tr '\n' ' ' | xargs)"
  log "Installing packages: ${packages[*]}"

  case "$manager" in
    apt-get)
      run_privileged apt-get update
      run_privileged apt-get install -y "${packages[@]}"
      ;;
    dnf)
      run_privileged dnf install -y "${packages[@]}"
      ;;
    yum)
      run_privileged yum install -y "${packages[@]}"
      ;;
    pacman)
      run_privileged pacman -Sy --noconfirm "${packages[@]}"
      ;;
    zypper)
      run_privileged zypper --non-interactive install "${packages[@]}"
      ;;
  esac
}

main() {
  local os_name
  local missing_after=()

  os_name="$(uname -s)"
  case "$os_name" in
    Darwin)
      install_with_brew
      ;;
    Linux)
      local linux_manager
      linux_manager="$(detect_linux_pkg_manager || true)"
      if [[ -z "$linux_manager" ]]; then
        log "Unsupported Linux distribution: no supported package manager found."
        exit 1
      fi
      install_with_linux_manager "$linux_manager"
      ;;
    *)
      log "Unsupported operating system: $os_name"
      exit 1
      ;;
  esac

  while IFS= read -r line; do
    [[ -n "$line" ]] && missing_after+=("$line")
  done < <(all_missing_requirements || true)

  echo
  if [[ ${#missing_after[@]} -eq 0 ]]; then
    log "All required system dependencies are available: ${REQUIRED_COMMANDS[*]}, libtoolize/glibtoolize, and bear/intercept-build"
  else
    log "Some commands are still missing: ${missing_after[*]}"
    log "You may need to add toolchain binaries to PATH or install distro-specific packages."
  fi

  if [[ "$os_name" == "Darwin" ]] && ! have_command clangd; then
    log 'If llvm was installed by Homebrew, add it to PATH: export PATH="/opt/homebrew/opt/llvm/bin:$PATH"'
  fi
}

main "$@"
