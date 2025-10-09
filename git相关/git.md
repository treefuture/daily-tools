# git 

软回退(Soft Reset):保留工作区和暂存区的更改,仅撤销提较

git reset --soft HEAD~1

硬回退(Hard Reset):撤销提交,并丢弃工作区和暂存区的角所有更改

git reset --hard HEAD~1

一键回到合并前状态，**工作区 & 暂存区** 都恢复。

git reset --merge HEAD

 通过**创建一个新的提交**来“反做”指定提交的更改 

git revert <commit-hash>

执行压缩合并(将 合并的分支 的所有提交压缩为1个)

git merge --squash 合并的分支

提交压缩后的结果(需手动添加提交信息)

git commit -m <commit>

 Git: [STARTED] Preparing... 报错 卡死的时候使用方法越过钩子

```bash
git commit --no-verify -m "复制提交信息"
```