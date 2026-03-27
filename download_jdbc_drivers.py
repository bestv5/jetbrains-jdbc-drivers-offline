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

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available artifacts and let user select by number (supports multi-select: '1,3,5' or '1-3')",
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


def get_artifact_list(root):
    """获取带版本的 artifact 列表，返回 (id, version_count) 元组列表"""
    artifacts = root.findall(".//artifact")
    result = []
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        version_elems = artifact.findall("version")
        version_count = len(version_elems)
        result.append((artifact_id, version_count))
    return result


def list_artifacts(root):
    """显示带编号的驱动列表供用户选择"""
    artifact_list = get_artifact_list(root)

    print("\n" + "=" * 60)
    print("可下载的 JDBC 驱动列表：")
    print("=" * 60)

    for idx, (artifact_id, version_count) in enumerate(artifact_list, start=1):
        print(f"  {idx:2d}. {artifact_id} ({version_count} 个版本)")

    print("=" * 60)
    print("\n请输入要下载的驱动编号（支持多选）：")
    print("  - 逗号分隔：1,3,5")
    print("  - 范围输入：1-3")
    print("  - 混合使用：1,3-5,7")
    print("> ", end="")

    # 刷新输出确保提示符显示
    sys.stdout.flush()

    user_input = input().strip()
    
    # 当输入0时退出脚本
    if user_input == "0":
        print("退出脚本")
        sys.exit(0)
        
    return user_input, artifact_list


def parse_selection(user_input, artifact_list):
    """解析用户输入，返回选中的 artifact id 列表"""
    if not user_input:
        return [], []

    total_count = len(artifact_list)
    selected_indices = set()
    errors = []

    # 按逗号分割
    parts = user_input.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 检查是否是范围格式 (如 "1-3")
        if "-" in part:
            range_parts = part.split("-")
            if len(range_parts) != 2:
                errors.append(f"无效范围格式: {part}")
                continue

            try:
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
            except ValueError:
                errors.append(f"无效范围数字: {part}")
                continue

            if start < 1 or end > total_count or start > end:
                errors.append(f"范围超出有效编号 (1-{total_count}): {part}")
                continue

            for idx in range(start, end + 1):
                selected_indices.add(idx)

        else:
            # 单个数字
            try:
                idx = int(part)
            except ValueError:
                errors.append(f"无效数字: {part}")
                continue

            if idx < 1 or idx > total_count:
                errors.append(f"编号超出有效范围 (1-{total_count}): {idx}")
                continue

            selected_indices.add(idx)

    # 如果有错误，显示错误信息
    if errors:
        print("\n输入错误：")
        for error in errors:
            print(f"  - {error}")
        return [], errors

    # 转换为 artifact id 列表
    selected_ids = []
    for idx in sorted(selected_indices):
        artifact_id, _ = artifact_list[idx - 1]
        selected_ids.append(artifact_id)

    return selected_ids, []


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

    # 加载 XML
    print(f"Loading {XML_FILE}...")
    root = load_xml()

    # 参数互斥校验
    mode_count = sum([args.all, bool(args.ids), args.list])
    if mode_count == 0:
        print("Error: Please specify --all, --ids, or --list")
        print("Use --help for more information")
        sys.exit(1)

    if mode_count > 1:
        print("Error: Cannot specify more than one of --all, --ids, --list")
        print("Use --help for more information")
        sys.exit(1)

    # 获取目标 artifact IDs
    if args.all:
        target_ids = get_artifact_ids(root)
    elif args.list:
        # 交互式选择模式
        user_input, artifact_list = list_artifacts(root)
        selected_ids, errors = parse_selection(user_input, artifact_list)

        if errors:
            print("\n请重新运行并输入有效的编号")
            sys.exit(1)

        if not selected_ids:
            print("未选择任何驱动")
            sys.exit(0)

        # 去重（因为 XML 中可能有重复的 artifact id）
        target_ids = []
        for aid in selected_ids:
            if aid not in target_ids:
                target_ids.append(aid)

        print(f"\n已选择 {len(target_ids)} 个驱动：")
        for aid in target_ids:
            print(f"  - {aid}")
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
