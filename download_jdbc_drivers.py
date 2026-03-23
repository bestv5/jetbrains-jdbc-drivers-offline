#!/usr/bin/env python3
"""
JDBC Driver Downloader - Downloads JDBC drivers and LICENSE files from jdbc-drivers.xml
"""

import argparse
import os
import sys
from pathlib import Path

from lxml import etree
import requests


# Aliyun Maven repository URL
MAVEN_BASE_URL = "https://maven.aliyun.com/repository/public/"
XML_FILE = "jdbc-drivers.xml"
OUTPUT_DIR = "jdbc-drivers"


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download JDBC drivers and LICENSE files from jdbc-drivers.xml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--all", action="store_true", help="Download all artifacts")

    parser.add_argument(
        "--ids",
        type=str,
        help="Comma-separated list of artifact IDs to download (e.g., 'HSQLDB,MySQL ConnectorJ')",
    )

    return parser.parse_args()


def load_xml():
    """Load and parse jdbc-drivers.xml"""
    if not os.path.exists(XML_FILE):
        print(f"Error: {XML_FILE} not found in current directory")
        sys.exit(1)

    try:
        tree = etree.parse(XML_FILE)
        return tree.getroot()
    except etree.XMLSyntaxError as e:
        print(f"Error: Failed to parse {XML_FILE}: {e}")
        sys.exit(1)


def get_artifact_ids(root):
    """Get all artifact IDs from XML"""
    artifacts = root.findall(".//artifact")
    return [artifact.get("id") for artifact in artifacts]


def convert_maven_url(maven_coord):
    """
    Convert Maven coordinate to Aliyun Maven URL.
    Example: org.hsqldb:hsqldb:2.7.0 ->
    https://maven.aliyun.com/repository/public/org/hsqldb/hsqldb/2.7.0/hsqldb-2.7.0.jar
    """
    parts = maven_coord.split(":")
    if len(parts) != 3:
        return None

    group_id, artifact_id, version = parts
    jar_name = f"{artifact_id}-{version}.jar"
    group_path = group_id.replace(".", "/")
    url = f"{MAVEN_BASE_URL}{group_path}/{artifact_id}/{version}/{jar_name}"

    return url


def download_file(url, dest_path, artifact_id, version):
    """Download a file with progress display"""
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


def process_artifact(artifact_id, root, target_ids=None):
    """Process a single artifact and download its files"""
    artifact_elem = root.find(f".//artifact[@id='{artifact_id}']")
    if artifact_elem is None:
        print(f"Warning: Artifact '{artifact_id}' not found in XML")
        return 0

    version_elems = artifact_elem.findall("version")
    downloaded_count = 0

    print(f"\nProcessing: {artifact_id}")

    for version_elem in version_elems:
        version = version_elem.get("version")
        if not version:
            continue

        # Create output directory for this version
        version_dir = os.path.join(OUTPUT_DIR, artifact_id, version)

        # Process items in this version
        item_elems = version_elem.findall("item")

        for item in item_elems:
            item_type = item.get("type")
            url = item.get("url")
            name = item.get("name")

            if not url:
                continue

            # Skip type="native" and type="pack" items
            if item_type == "native" or item_type == "pack":
                continue

            # Handle type="maven" items
            if item_type == "maven":
                maven_url = convert_maven_url(url)
                if maven_url:
                    jar_name = f"{url.split(':')[1]}-{url.split(':')[2]}.jar"
                    dest_path = os.path.join(version_dir, jar_name)
                    if download_file(maven_url, dest_path, artifact_id, version):
                        downloaded_count += 1

            # Handle type="license" items
            elif item_type == "license":
                if name:
                    dest_name = name
                else:
                    # Extract filename from URL
                    dest_name = url.split("/")[-1]
                    if not dest_name:
                        dest_name = "LICENSE.txt"

                dest_path = os.path.join(version_dir, dest_name)
                if download_file(url, dest_path, artifact_id, version):
                    downloaded_count += 1

            # Handle items without type (direct URL like some ClickHouse entries)
            elif item_type is None and url:
                # Check if it's a JAR file URL
                if url.endswith(".jar"):
                    if name:
                        jar_name = name
                    else:
                        jar_name = url.split("/")[-1]

                    dest_path = os.path.join(version_dir, jar_name)
                    if download_file(url, dest_path, artifact_id, version):
                        downloaded_count += 1

    return downloaded_count


def main():
    """Main function"""
    args = parse_arguments()

    # Validate arguments
    if not args.all and not args.ids:
        print("Error: Please specify either --all or --ids")
        print("Use --help for more information")
        sys.exit(1)

    if args.all and args.ids:
        print("Error: Cannot specify both --all and --ids")
        print("Use --help for more information")
        sys.exit(1)

    # Load XML
    print(f"Loading {XML_FILE}...")
    root = load_xml()

    # Get target artifact IDs
    if args.all:
        target_ids = get_artifact_ids(root)
    else:
        target_ids = [aid.strip() for aid in args.ids.split(",")]

    print(f"Found {len(target_ids)} artifact(s) to process")

    # Process each artifact
    total_downloaded = 0
    for artifact_id in target_ids:
        count = process_artifact(artifact_id, root, target_ids)
        total_downloaded += count

    print(f"\n{'=' * 50}")
    print(f"Total files downloaded: {total_downloaded}")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
