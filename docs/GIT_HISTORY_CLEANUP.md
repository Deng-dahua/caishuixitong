# Git 历史密钥清理

历史重写是破坏性操作，必须在密钥撤销后、所有协作者知情且仓库已做镜像备份时执行。

1. 立即在密钥供应商控制台撤销旧密钥并创建新密钥。
2. 暂停合并，创建仓库镜像备份。
3. 安装 `git-filter-repo`，在镜像克隆中删除敏感文件：

```bash
git filter-repo --path static/api_key.json --path sessions.json \
  --path access_logs.jsonl --path accounting.db --invert-paths
```

4. 用替换文件清除其他提交内容中的密钥原文，再复查所有分支和标签。
5. 强制推送重写后的分支/标签，要求所有协作者重新克隆。
6. 检查 CI 日志、发布制品、缓存、Fork 和远端备份；这些副本不会自动被清理。

不要在命令行或工单中粘贴旧密钥。清理 Git 历史不能替代密钥撤销。
