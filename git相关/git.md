# git 

软回退(Soft Reset):保留工作区和暂存区的更改,仅撤销提较

```
git reset --soft HEAD~1
```

硬回退(Hard Reset):撤销提交,并丢弃工作区和暂存区的角所有更改

```
git reset --hard HEAD~1
```

一键回到合并前状态，**工作区 & 暂存区** 都恢复。

```
git reset --merge HEAD
```

 通过**创建一个新的提交**来“反做”指定提交的更改 

```
git revert <commit-hash>
```

执行压缩合并(将 合并的分支 的所有提交压缩为1个)

```
git merge --squash 合并的分支
```

 合并特定的提交(可以有多个合并哈希)，可以用于 压缩合并后 revert 某个提交导致不能合并的问题 

```
git cherry-pick <commit-hash>
```

 如果 `cherry-pick` 的提交有误，可以使用 `--abort` 选项撤销操作 

```
git cherry-pick --abort
```

提交压缩后的结果(需手动添加提交信息)

```
git commit -m <commit>
```

Git: [STARTED] Preparing... 报错 卡死的时候使用方法越过钩子

```bash
git commit --no-verify -m "复制提交信息"
```

将提交存入暂存区

```
git stash save "提交信息"
git stash list // 查看暂存区列表
git stash apply (数字或名称) // 要使用的暂存提交
git stahs drop  (数字或名称) // 要删除的暂存提交

```

恢复错误删除的暂存区信息

```
git reflog // 查看引用日志
git stash apply xxx(数字) // 恢复 stash
git stash pop xxx(数字)   // 恢复并删除这个 stash

如果 git reflog 没有找到被删除的 stash，你可以尝试使用 git fsck 来查找丢失的对象
git fsck --full --no-reflogs --unreachable --lost-found // 这个命令会列出所有未引用的对象，包括丢失的 stash
```

