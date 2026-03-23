# jetbrains-jdbc-drivers-offline
下载jetbrains DataGrip数据库驱动，理论上其他工具比如idea也可以用。用于复制到离线环境下使用。

# 功能说明
解析jdbc-drivers.xml，进行下载驱动文件。
也可以从jetbrains网站在线获取最新jdbc-drivers.xml，更新本地驱动。
下载源: 使用阿里云 Maven 镜像 (https://maven.aliyun.com/repository/public/)

# 已有脚本对比
| 脚本 | 用途 |
|------|------|
| download_jdbc_drivers.py | 首次下载（指定artifact或全部） |
| update_jdbc_drivers.py | 增量更新（自动检测新版本） |


# 使用说明
1、download_jdbc_drivers.py
```bash
# Download all artifacts
python3 download_jdbc_drivers.py --all

# Download specific artifacts
python3 download_jdbc_drivers.py --ids "HSQLDB,MySQL ConnectorJ,PostgreSQL 2"
```

2 脚本文件: update_jdbc_drivers.py
功能
| 命令 | 说明 |
|------|------|
| update | 下载远程XML + 增量下载新驱动 + 更新本地XML |
| cleanup | 列出可删除的版本（本地有但远程没有） |
| delete <indices> | 根据序号删除版本（支持 "1,3,5" 或 "1-3" 格式） |
使用示例
# 增量更新（推荐）
python3 update_jdbc_drivers.py update
# 查看哪些可以删除
python3 update_jdbc_drivers.py cleanup
# 删除序号1和3的版本
python3 update_jdbc_drivers.py delete "1,3"
# 或删除范围 1-5
python3 update_jdbc_drivers.py delete "1-5"
# 强制删除（跳过确认）
python3 update_jdbc_drivers.py delete "1" --force
