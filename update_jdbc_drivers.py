#!/usr/bin/env python3
"""
JDBC Driver Update Manager - Manages JDBC driver updates, cleanup, and deletion
"""

import argparse
import os
import sys
import shutil
from pathlib import Path

from lxml import etree
import requests

# Constants
REMOTE_XML_URL = "https://frameworks.jetbrains.com/jdbc-drivers/jdbc-drivers.xml"
LOCAL_XML = "jdbc-drivers.xml"
TEMP_XML = "jdbc-drivers.xml.new"
OUTPUT_DIR = "jdbc-drivers"
MAVEN_BASE_URL = "https://maven.aliyun.com/repository/public/"


def parse_arguments():
    """Parse command line arguments with subcommands."""
    parser = argparse.ArgumentParser(
        description="JDBC Driver Update Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # update subcommand
    update_parser = subparsers.add_parser(
        "update", help="Download remote XML and incrementally update drivers"
    )

    # cleanup subcommand
    cleanup_parser = subparsers.add_parser(
        "cleanup", help="List local versions that no longer exist in remote XML"
    )

    # delete subcommand
    delete_parser = subparsers.add_parser(
        "delete", help="Delete versions by index (e.g., '1,3,5' or '1-3')"
    )
    delete_parser.add_argument(
        "indices",
        type=str,
        help="Comma-separated indices or ranges (e.g., '1,3,5' or '1-3')",
    )
    delete_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )

    return parser.parse_args()


def download_remote_xml():
    """Download remote jdbc-drivers.xml"""
    try:
        print(f"Downloading remote XML from {REMOTE_XML_URL}...")
        response = requests.get(REMOTE_XML_URL, timeout=60)
        response.raise_for_status()

        with open(TEMP_XML, "wb") as f:
            f.write(response.content)

        print(f"Remote XML saved to {TEMP_XML}")
        return True
    except requests.RequestException as e:
        print(f"Error: Failed to download remote XML: {e}")
        return False


def parse_xml(xml_file):
    """Parse and return XML root"""
    try:
        tree = etree.parse(xml_file)
        return tree.getroot()
    except etree.XMLSyntaxError as e:
        print(f"Error: Failed to parse {xml_file}: {e}")
        return None


def get_remote_artifacts(root):
    """Get all (artifact_id, version) pairs from remote XML"""
    artifacts = []
    for artifact_elem in root.findall(".//artifact"):
        artifact_id = artifact_elem.get("id")
        if not artifact_id:
            continue

        for version_elem in artifact_elem.findall("version"):
            version = version_elem.get("version")
            if version:
                artifacts.append((artifact_id, version))

    return artifacts


def get_local_artifacts():
    """Get all (artifact_id, version) pairs from local jdbc-drivers directory"""
    artifacts = []
    output_path = Path(OUTPUT_DIR)

    if not output_path.exists():
        return artifacts

    for artifact_dir in output_path.iterdir():
        if not artifact_dir.is_dir():
            continue

        artifact_id = artifact_dir.name
        for version_dir in artifact_dir.iterdir():
            if not version_dir.is_dir():
                continue

            version = version_dir.name
            artifacts.append((artifact_id, version))

    return artifacts


def convert_maven_url(maven_coord):
    """Convert Maven coordinate to Aliyun Maven URL"""
    parts = maven_coord.split(":")
    if len(parts) != 3:
        return None

    group_id, artifact_id, version = parts
    jar_name = f"{artifact_id}-{version}.jar"
    group_path = group_id.replace(".", "/")
    url = f"{MAVEN_BASE_URL}{group_path}/{artifact_id}/{version}/{jar_name}"

    return url


def download_file(url, dest_path, artifact_id, version):
    """Download a file"""
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        with open(dest_path, "wb") as f:
            f.write(response.content)

        size = len(response.content)
        print(
            f"  [OK] {artifact_id}/{version}: {os.path.basename(dest_path)} ({size:,} bytes)"
        )
        return True

    except requests.RequestException as e:
        print(f"  [FAIL] {artifact_id}/{version}: {os.path.basename(dest_path)} - {e}")
        return False


def process_artifact(artifact_id, version, root):
    """Download files for a specific artifact version"""
    artifact_elem = root.find(f".//artifact[@id='{artifact_id}']")
    if artifact_elem is None:
        return 0

    version_elem = artifact_elem.find(f"version[@version='{version}']")
    if version_elem is None:
        return 0

    version_dir = os.path.join(OUTPUT_DIR, artifact_id, version)
    downloaded_count = 0

    for item in version_elem.findall("item"):
        item_type = item.get("type")
        url = item.get("url")
        name = item.get("name")

        if not url:
            continue

        # Skip type="native" and type="pack" items
        if item_type == "native" or item_type == "pack":
            continue

        if item_type == "maven":
            maven_url = convert_maven_url(url)
            if maven_url:
                jar_name = f"{url.split(':')[1]}-{url.split(':')[2]}.jar"
                dest_path = os.path.join(version_dir, jar_name)
                if download_file(maven_url, dest_path, artifact_id, version):
                    downloaded_count += 1

        elif item_type == "license":
            if name:
                dest_name = name
            else:
                dest_name = url.split("/")[-1]
                if not dest_name:
                    dest_name = "LICENSE.txt"

            dest_path = os.path.join(version_dir, dest_name)
            if download_file(url, dest_path, artifact_id, version):
                downloaded_count += 1

        elif item_type is None and url:
            if url.endswith(".jar"):
                if name:
                    jar_name = name
                else:
                    jar_name = url.split("/")[-1]

                dest_path = os.path.join(version_dir, jar_name)
                if download_file(url, dest_path, artifact_id, version):
                    downloaded_count += 1

    return downloaded_count


def cmd_update(args):
    """Handle update command"""
    # Download remote XML
    if not download_remote_xml():
        sys.exit(1)

    # Parse remote XML
    remote_root = parse_xml(TEMP_XML)
    if remote_root is None:
        sys.exit(1)

    # Parse local XML if exists
    local_root = None
    if os.path.exists(LOCAL_XML):
        local_root = parse_xml(LOCAL_XML)

    # Get remote artifacts
    remote_artifacts = get_remote_artifacts(remote_root)
    print(f"\nRemote XML contains {len(remote_artifacts)} artifact versions")

    # Get local artifacts
    local_artifacts = get_local_artifacts()
    print(f"Local directory contains {len(local_artifacts)} artifact versions")

    # Find new artifacts (in remote but not in local)
    local_set = set(local_artifacts)
    new_artifacts = [
        (aid, ver) for aid, ver in remote_artifacts if (aid, ver) not in local_set
    ]

    print(f"\nFound {len(new_artifacts)} new versions to download")

    if not new_artifacts:
        print("No new drivers to download")
        # Replace old XML with new
        shutil.move(TEMP_XML, LOCAL_XML)
        print(f"Updated {LOCAL_XML}")
        return

    # Download new artifacts
    total_downloaded = 0
    for artifact_id, version in new_artifacts:
        print(f"\nDownloading: {artifact_id} {version}")
        count = process_artifact(artifact_id, version, remote_root)
        total_downloaded += count

    print(f"\n{'=' * 50}")
    print(f"Total files downloaded: {total_downloaded}")

    # Replace old XML with new
    if os.path.exists(LOCAL_XML):
        os.remove(LOCAL_XML)
    shutil.move(TEMP_XML, LOCAL_XML)
    print(f"Updated {LOCAL_XML}")


def cmd_cleanup(args):
    """Handle cleanup command"""
    # Download remote XML
    if not download_remote_xml():
        sys.exit(1)

    # Parse remote XML
    remote_root = parse_xml(TEMP_XML)
    if remote_root is None:
        sys.exit(1)

    # Get remote artifacts
    remote_artifacts = get_remote_artifacts(remote_root)
    remote_set = set(remote_artifacts)
    print(f"Remote XML contains {len(remote_artifacts)} artifact versions")

    # Get local artifacts
    local_artifacts = get_local_artifacts()
    print(f"Local directory contains {len(local_artifacts)} artifact versions")

    # Find orphaned artifacts (in local but not in remote)
    orphans = [
        (aid, ver) for aid, ver in local_artifacts if (aid, ver) not in remote_set
    ]

    # Clean up temp file
    if os.path.exists(TEMP_XML):
        os.remove(TEMP_XML)

    if not orphans:
        print("\nNo orphaned versions found")
        return

    print(f"\nFound {len(orphans)} orphaned version(s) that can be deleted:")
    print("-" * 50)

    for i, (artifact_id, version) in enumerate(orphans, 1):
        print(f"  [{i}] {artifact_id}/{version}")

    print("-" * 50)
    print(f"\nTo delete, run: python3 update_jdbc_drivers.py delete <indices>")


def parse_indices(indices_str):
    """Parse indices string like '1,3,5' or '1-3' into list of integers"""
    indices = []
    parts = indices_str.split(",")

    for part in parts:
        part = part.strip()
        if "-" in part:
            # Range like "1-3"
            start, end = part.split("-", 1)
            start = int(start.strip())
            end = int(end.strip())
            indices.extend(range(start, end + 1))
        else:
            # Single index
            indices.append(int(part))

    return sorted(set(indices))


def cmd_delete(args):
    """Handle delete command"""
    # Parse indices
    try:
        indices = parse_indices(args.indices)
    except ValueError as e:
        print(f"Error: Invalid indices format: {e}")
        sys.exit(1)

    # Get local artifacts
    local_artifacts = get_local_artifacts()

    if not local_artifacts:
        print("No local artifacts found")
        sys.exit(1)

    # Get remote artifacts for comparison
    if not download_remote_xml():
        # Continue even if download fails, we still have local artifacts
        remote_set = set()
    else:
        remote_root = parse_xml(TEMP_XML)
        if remote_root:
            remote_set = set(get_remote_artifacts(remote_root))
        else:
            remote_set = set()

        if os.path.exists(TEMP_XML):
            os.remove(TEMP_XML)

    # Find orphans
    orphans = [
        (aid, ver) for aid, ver in local_artifacts if (aid, ver) not in remote_set
    ]

    # Validate indices
    if not orphans:
        print("No orphaned versions to delete")
        sys.exit(1)

    max_index = len(orphans)
    for idx in indices:
        if idx < 1 or idx > max_index:
            print(f"Error: Index {idx} out of range (1-{max_index})")
            sys.exit(1)

    # Confirm deletion
    if not args.force:
        print("The following versions will be deleted:")
        for idx in indices:
            artifact_id, version = orphans[idx - 1]
            print(f"  [{idx}] {artifact_id}/{version}")

        response = input("\nConfirm deletion (yes/no): ")
        if response.lower() not in ("yes", "y"):
            print("Deletion cancelled")
            sys.exit(0)

    # Delete artifacts
    deleted_count = 0
    for idx in indices:
        artifact_id, version = orphans[idx - 1]
        version_dir = os.path.join(OUTPUT_DIR, artifact_id, version)

        try:
            shutil.rmtree(version_dir)
            print(f"Deleted: {artifact_id}/{version}")
            deleted_count += 1
        except OSError as e:
            print(f"Error deleting {artifact_id}/{version}: {e}")

    print(f"\nTotal versions deleted: {deleted_count}")


def main():
    """Main function"""
    args = parse_arguments()

    if args.command is None:
        print("Error: Please specify a command (update, cleanup, or delete)")
        print("Use --help for more information")
        sys.exit(1)

    if args.command == "update":
        cmd_update(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    elif args.command == "delete":
        cmd_delete(args)


if __name__ == "__main__":
    main()
