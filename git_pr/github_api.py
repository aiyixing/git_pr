import os
import re
import subprocess
from pathlib import Path
from github import Github, GithubException
from .config import ConfigManager


class GitHubAPI:
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.token = self.config.get_github_token()
        self._config_username = self.config.get_github_username()
        self.default_branch = self.config.get_default_branch()
        self.g = Github(self.token) if self.token else None
        self._github_user = None

    def _get_github_user(self):
        if self._github_user:
            return self._github_user
        if self.g:
            try:
                user = self.g.get_user()
                _ = user.login
                self._github_user = user
                return self._github_user
            except Exception:
                return None
        return None

    def _get_github_username(self):
        user = self._get_github_user()
        if user:
            try:
                return user.login
            except Exception:
                pass
        return None

    @property
    def username(self):
        token_username = self._get_github_username()
        if token_username:
            return token_username
        return self._config_username

    def _run_git_command(self, args, cwd=None):
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True
            )
            return {
                "success": True,
                "output": result.stdout.strip(),
                "error": result.stderr.strip()
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "output": e.stdout.strip(),
                "error": e.stderr.strip()
            }

    def _validate_git_repo(self, dir_path: Path):
        if not (dir_path / ".git").exists():
            return {
                "valid": False,
                "error": f"目录 '{dir_path}' 不是一个git仓库。",
                "suggestion": f"请先执行: gitpr create-repo {dir_path}"
            }
        
        remote_result = self._run_git_command(["remote", "-v"], cwd=str(dir_path))
        if not remote_result["success"] or not remote_result["output"]:
            return {
                "valid": False,
                "error": f"git仓库 '{dir_path}' 没有配置远程仓库(remote)。",
                "suggestion": "请先执行 'gitpr create-repo' 创建远程仓库并关联。"
            }
        
        return {"valid": True}

    def _has_commits(self, dir_path: Path):
        log_result = self._run_git_command(["log", "--oneline", "-n", "1"], cwd=str(dir_path))
        return log_result["success"] and bool(log_result["output"])

    def _get_current_branch(self, dir_path: Path):
        branch_result = self._run_git_command(["branch", "--show-current"], cwd=str(dir_path))
        if branch_result["success"]:
            return branch_result["output"]
        return None

    def _check_remote_repo_exists(self, repo_name: str):
        if not self.g:
            return {
                "exists": False,
                "error": "GitHub未配置。请先运行 'gitpr config'。"
            }

        username = self._get_github_username()
        if not username:
            return {
                "exists": False,
                "error": "无法通过TOKEN获取GitHub用户信息。",
                "suggestion": "请检查TOKEN是否有效，需要repo权限。"
            }

        try:
            repo = self.g.get_repo(f"{username}/{repo_name}")
            return {
                "exists": True,
                "repo": repo,
                "username": username
            }
        except GithubException as e:
            if e.status == 404:
                return {
                    "exists": False,
                    "error": f"远程仓库 '{username}/{repo_name}' 不存在。",
                    "suggestion": f"请先执行 'gitpr create-repo' 创建仓库。",
                    "username": username,
                    "repo_name": repo_name
                }
            return {
                "exists": False,
                "error": f"检查仓库时出错: {e.data.get('message', str(e))}",
                "username": username
            }

    def create_repository(self, directory_path: str):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        if not self.g:
            return {
                "success": False,
                "error": "GitHub未配置。请先运行 'gitpr config'。",
                "repo_name": repo_name
            }

        user = self._get_github_user()
        if not user:
            return {
                "success": False,
                "error": "无法通过TOKEN获取GitHub用户信息。",
                "suggestion": "请检查TOKEN是否有效，需要repo权限。",
                "repo_name": repo_name
            }

        try:
            repo = user.create_repo(repo_name, private=False)
            
            if not (dir_path / ".git").exists():
                init_result = self._run_git_command(["init"], cwd=str(dir_path))
                if not init_result["success"]:
                    return {
                        "success": False,
                        "error": f"git init失败: {init_result['error']}",
                        "repo_name": repo_name
                    }
            
            remote_result = self._run_git_command(
                ["remote", "add", "origin", repo.clone_url],
                cwd=str(dir_path)
            )
            if not remote_result["success"] and "remote origin already exists" not in remote_result["error"]:
                return {
                    "success": False,
                    "error": f"添加远程仓库失败: {remote_result['error']}",
                    "repo_name": repo_name
                }

            return {
                "success": True,
                "repo_name": repo_name,
                "repo_url": repo.html_url,
                "clone_url": repo.clone_url,
                "username": user.login,
                "directory": str(dir_path),
                "message": f"仓库 '{repo_name}' 创建成功。下一步请使用 'gitpr commit' 提交代码。",
                "next_step": f"gitpr commit {dir_path} \"初始化提交\""
            }
        except GithubException as e:
            error_msg = e.data.get('message', str(e))
            if "already exists" in error_msg:
                return {
                    "success": False,
                    "error": f"仓库 '{repo_name}' 已存在于GitHub。",
                    "repo_name": repo_name,
                    "username": user.login,
                    "suggestion": "如果本地目录未关联，请手动执行: git remote add origin <仓库地址>"
                }
            return {
                "success": False,
                "error": f"GitHub API错误: {error_msg}",
                "repo_name": repo_name,
                "username": user.login
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "repo_name": repo_name
            }

    def commit_and_push(self, directory_path: str, commit_message: str):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        validation = self._validate_git_repo(dir_path)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["error"],
                "suggestion": validation.get("suggestion"),
                "repo_name": repo_name
            }

        if not self.g:
            return {
                "success": False,
                "error": "GitHub未配置。请先运行 'gitpr config'。"
            }

        add_result = self._run_git_command(["add", "."], cwd=str(dir_path))
        if not add_result["success"]:
            return {
                "success": False,
                "error": f"添加文件失败: {add_result['error']}",
                "repo_name": repo_name
            }

        commit_result = self._run_git_command(
            ["commit", "-m", commit_message],
            cwd=str(dir_path)
        )
        if not commit_result["success"]:
            if "nothing to commit" in commit_result["error"] or "nothing added to commit" in commit_result["error"]:
                return {
                    "success": True,
                    "message": "没有需要提交的更改，工作区干净。",
                    "commit_message": commit_message,
                    "repo_name": repo_name
                }
            return {
                "success": False,
                "error": f"提交失败: {commit_result['error']}",
                "repo_name": repo_name
            }

        current_branch = self._get_current_branch(dir_path)
        
        if not current_branch:
            return {
                "success": False,
                "error": "无法获取当前分支。",
                "repo_name": repo_name,
                "suggestion": "请确保仓库有提交记录。"
            }

        push_result = self._run_git_command(
            ["push", "-u", "origin", current_branch],
            cwd=str(dir_path)
        )
        if not push_result["success"]:
            return {
                "success": False,
                "error": f"推送失败: {push_result['error']}",
                "repo_name": repo_name,
                "branch": current_branch,
                "suggestion": "请检查网络连接、GitHub权限或分支是否存在。"
            }

        username = self._get_github_username()
        branch_info = {
            "current_branch": current_branch,
            "default_branch": self.default_branch
        }
        
        if current_branch != self.default_branch:
            branch_info["warning"] = f"当前分支 '{current_branch}' 与配置的默认分支 '{self.default_branch}' 不同。创建PR时请注意分支设置。"

        return {
            "success": True,
            "message": f"提交并推送成功: {commit_message}",
            "commit_message": commit_message,
            "branch_info": branch_info,
            "repo_name": repo_name,
            "username": username if username else self._config_username,
            "next_step": f"下一步可执行: gitpr create-pr {dir_path} \"{commit_message}\""
        }

    def create_pull_request(self, directory_path: str, title: str, head_branch: str = None, base_branch: str = None):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        validation = self._validate_git_repo(dir_path)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["error"],
                "suggestion": validation.get("suggestion"),
                "repo_name": repo_name
            }

        if not self._has_commits(dir_path):
            return {
                "success": False,
                "error": f"仓库 '{repo_name}' 没有任何提交记录。",
                "repo_name": repo_name,
                "suggestion": f"请先执行: gitpr commit {dir_path} \"提交信息\""
            }

        if not self.g:
            return {
                "success": False,
                "error": "GitHub未配置。请先运行 'gitpr config'。"
            }

        repo_check = self._check_remote_repo_exists(repo_name)
        if not repo_check["exists"]:
            return {
                "success": False,
                "error": repo_check["error"],
                "suggestion": repo_check.get("suggestion"),
                "repo_name": repo_name,
                "username": repo_check.get("username")
            }

        username = self._get_github_username()
        if not username:
            username = self._config_username

        current_branch = self._get_current_branch(dir_path)
        
        if head_branch is None:
            head_branch = current_branch or self.default_branch
        if base_branch is None:
            base_branch = self.default_branch

        branch_info = {
            "head_branch": head_branch,
            "base_branch": base_branch,
            "current_local_branch": current_branch
        }

        if head_branch == base_branch:
            return {
                "success": False,
                "error": "源分支和目标分支相同，无法创建Pull Request。",
                "repo_name": repo_name,
                "username": username,
                "branch_info": branch_info,
                "suggestion": "\n".join([
                    f"当前配置: head_branch='{head_branch}', base_branch='{base_branch}'",
                    f"解决方案1: 使用不同的分支，例如: gitpr create-pr {dir_path} \"标题\" --head {head_branch} --base develop",
                    f"解决方案2: 如果你想快速测试，可以使用 --merge 参数配合 full 命令，它会自动处理。"
                ])
            }

        try:
            repo = repo_check["repo"]
            
            try:
                repo.get_branch(head_branch)
            except GithubException:
                return {
                    "success": False,
                    "error": f"源分支 '{head_branch}' 在远程仓库不存在。",
                    "repo_name": repo_name,
                    "username": username,
                    "branch_info": branch_info,
                    "suggestion": f"请先将本地分支推送到远程: git push -u origin {head_branch}"
                }

            try:
                repo.get_branch(base_branch)
            except GithubException:
                return {
                    "success": False,
                    "error": f"目标分支 '{base_branch}' 在远程仓库不存在。",
                    "repo_name": repo_name,
                    "username": username,
                    "branch_info": branch_info,
                    "suggestion": "\n".join([
                        f"配置的默认分支是 '{self.default_branch}', 但远程仓库没有这个分支。",
                        f"你可以: ",
                        f"  1. 指定存在的分支: gitpr create-pr {dir_path} \"标题\" --base {head_branch}",
                        f"  2. 或者修改默认分支配置: gitpr config --branch {head_branch}"
                    ])
                }

            pr = repo.create_pull(
                title=title,
                body=f"Pull request created by gitpr CLI\nTitle: {title}",
                head=head_branch,
                base=base_branch
            )

            return {
                "success": True,
                "pr_number": pr.number,
                "pr_title": pr.title,
                "pr_url": pr.html_url,
                "pr_state": pr.state,
                "branch_info": branch_info,
                "repo_name": repo_name,
                "username": username,
                "message": f"Pull request 创建成功: #{pr.number}",
                "next_step": f"可执行合并: gitpr merge {dir_path} {pr.number}"
            }
        except GithubException as e:
            error_msg = e.data.get('message', str(e))
            errors = e.data.get('errors', [])
            
            detailed_errors = []
            for err in errors:
                detailed_errors.append(f"{err.get('field', '')}: {err.get('message', '')}")
            
            suggestion = ""
            
            if "No commits between" in error_msg or "does not contain any commits" in error_msg:
                suggestion = f"源分支 '{head_branch}' 和目标分支 '{base_branch}' 之间没有差异。请确保有新的提交。"
            elif "A pull request already exists" in error_msg:
                suggestion = "已存在相同分支的Pull Request。请先关闭或合并现有的PR。"
            elif "Validation Failed" in error_msg:
                suggestion_parts = [
                    f"PR创建验证失败。",
                    f"当前配置: head='{head_branch}' -> base='{base_branch}'",
                    ""
                ]
                if detailed_errors:
                    suggestion_parts.extend(detailed_errors)
                else:
                    display_username = username if username else 'username'
                    suggestion_parts.extend([
                        "可能的原因:",
                        f"  1. 源分支 '{head_branch}' 不存在于远程",
                        f"  2. 目标分支 '{base_branch}' 不存在于远程",
                        f"  3. 两个分支之间没有差异",
                        f"  4. 源分支和目标分支相同",
                        "",
                        f"当前本地分支: '{current_branch}'",
                        f"配置的默认分支: '{self.default_branch}'",
                        "",
                        "建议:",
                        f"  - 如果只有一个分支，使用 full 命令: gitpr full {dir_path} \"标题\" --merge",
                        f"  - 或者检查远程仓库分支: https://github.com/{display_username}/{repo_name}/branches"
                    ])
                suggestion = "\n".join(suggestion_parts)
            
            return {
                "success": False,
                "error": f"GitHub API错误: {error_msg}",
                "repo_name": repo_name,
                "username": username,
                "branch_info": branch_info,
                "detailed_errors": detailed_errors,
                "suggestion": suggestion
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "repo_name": repo_name
            }

    def merge_pull_request(self, directory_path: str, pr_number: int, merge_method: str = "merge"):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        if not self.g:
            return {
                "success": False,
                "error": "GitHub未配置。请先运行 'gitpr config'。"
            }

        repo_check = self._check_remote_repo_exists(repo_name)
        if not repo_check["exists"]:
            return {
                "success": False,
                "error": repo_check["error"],
                "suggestion": repo_check.get("suggestion"),
                "pr_number": pr_number
            }

        username = self._get_github_username()
        if not username:
            username = self._config_username

        try:
            repo = repo_check["repo"]
            pr = repo.get_pull(pr_number)

            if pr.state != "open":
                return {
                    "success": False,
                    "error": f"Pull request #{pr_number} 状态为 '{pr.state}'，无法合并。",
                    "pr_number": pr_number,
                    "pr_state": pr.state,
                    "username": username
                }

            if not pr.mergeable:
                mergeable_state = pr.mergeable_state
                suggestion = ""
                if mergeable_state == "behind":
                    suggestion = "目标分支有新的提交，请先更新源分支。"
                elif mergeable_state == "dirty":
                    suggestion = "存在合并冲突，请先解决冲突。"
                elif mergeable_state == "unknown":
                    suggestion = "合并状态未知，请稍后重试或在GitHub网页上检查。"
                
                return {
                    "success": False,
                    "error": f"Pull request #{pr_number} 不可合并 (状态: {mergeable_state})",
                    "pr_number": pr_number,
                    "username": username,
                    "suggestion": suggestion
                }

            merge_result = pr.merge(
                merge_method=merge_method,
                commit_title=f"Merge PR #{pr_number}: {pr.title}"
            )

            return {
                "success": True,
                "pr_number": pr_number,
                "pr_title": pr.title,
                "pr_url": pr.html_url,
                "merged": merge_result.merged,
                "sha": merge_result.sha,
                "merge_method": merge_method,
                "username": username,
                "message": f"Pull request #{pr_number} 合并成功"
            }
        except GithubException as e:
            error_msg = e.data.get('message', str(e))
            return {
                "success": False,
                "error": f"GitHub API错误: {error_msg}",
                "pr_number": pr_number,
                "username": username
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "pr_number": pr_number
            }

    def full_workflow(self, directory_path: str, title: str, merge: bool = False, merge_method: str = "merge"):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        steps = []
        results = {}

        create_result = self.create_repository(directory_path)
        results["create_repo"] = create_result
        steps.append(f"创建仓库: {'成功' if create_result['success'] else '失败'}")
        
        if not create_result["success"]:
            error_lower = create_result.get("error", "").lower()
            if "already exists" not in error_lower and "已存在" not in error_lower:
                return {
                    "success": False,
                    "error": f"创建仓库失败: {create_result['error']}",
                    "steps": steps,
                    "results": results
                }

        commit_result = self.commit_and_push(directory_path, title)
        results["commit"] = commit_result
        steps.append(f"提交代码: {'成功' if commit_result['success'] else '失败'}")
        
        if not commit_result["success"]:
            return {
                "success": False,
                "error": f"提交代码失败: {commit_result['error']}",
                "steps": steps,
                "results": results
            }

        pr_result = None
        need_merge = merge
        
        username = self._get_github_username()
        if not username:
            username = self._config_username
        
        current_branch = commit_result.get("branch_info", {}).get("current_branch")
        default_branch = self.default_branch
        
        if current_branch and current_branch == default_branch:
            pr_skip_reason = f"当前分支 '{current_branch}' 与默认分支 '{default_branch}' 相同，跳过PR创建。"
            steps.append(f"跳过PR创建: 分支相同")
            
            result = {
                "success": True,
                "repo_name": repo_name,
                "repo_url": create_result.get("repo_url"),
                "commit_message": title,
                "pr_skipped": True,
                "pr_skip_reason": pr_skip_reason,
                "username": username,
                "branch_info": {
                    "current_branch": current_branch,
                    "default_branch": default_branch
                },
                "steps": steps,
                "results": results,
                "message": "工作流完成: 仓库创建 -> 代码提交 (PR跳过: 分支相同)"
            }
            
            if need_merge:
                result["message"] += " (无需合并)"
            
            return result

        pr_result = self.create_pull_request(directory_path, title)
        results["create_pr"] = pr_result
        steps.append(f"创建PR: {'成功' if pr_result['success'] else '失败'}")
        
        if not pr_result["success"]:
            return {
                "success": False,
                "error": f"创建PR失败: {pr_result.get('error', '未知错误')}",
                "steps": steps,
                "results": results
            }

        result = {
            "success": True,
            "repo_name": repo_name,
            "repo_url": create_result.get("repo_url"),
            "commit_message": title,
            "pr_number": pr_result["pr_number"],
            "pr_title": pr_result["pr_title"],
            "pr_url": pr_result["pr_url"],
            "pr_state": pr_result["pr_state"],
            "username": username,
            "steps": steps,
            "results": results,
            "message": "完整工作流完成: 仓库创建 -> 代码提交 -> PR创建"
        }

        if need_merge:
            merge_result = self.merge_pull_request(directory_path, pr_result["pr_number"], merge_method)
            results["merge"] = merge_result
            steps.append(f"合并PR: {'成功' if merge_result['success'] else '失败'}")
            result["merge_result"] = merge_result
            
            if merge_result["success"]:
                result["message"] += " -> PR合并"
            else:
                result["merge_error"] = merge_result.get("error")
                result["message"] += " -> PR合并失败"

        result["steps"] = steps
        return result

    def delete_repository(self, repo_name: str):
        if not self.g:
            return {
                "success": False,
                "error": "GitHub未配置。请先运行 'gitpr config'。"
            }

        username = self._get_github_username()
        if not username:
            username = self._config_username

        try:
            repo = self.g.get_repo(f"{username}/{repo_name}")
            repo.delete()
            
            return {
                "success": True,
                "repo_name": repo_name,
                "username": username,
                "message": f"仓库 '{username}/{repo_name}' 已成功删除"
            }
        except GithubException as e:
            if e.status == 404:
                return {
                    "success": False,
                    "error": f"仓库 '{username}/{repo_name}' 不存在。",
                    "repo_name": repo_name,
                    "username": username
                }
            return {
                "success": False,
                "error": f"GitHub API错误: {e.data.get('message', str(e))}",
                "repo_name": repo_name,
                "username": username
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "repo_name": repo_name
            }

    def auto_pr_workflow(self, directory_path: str, title: str, 
                          base_branch: str = None, 
                          head_branch: str = None,
                          merge: bool = False,
                          merge_method: str = "merge",
                          force_clean: bool = False):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        steps = []
        results = {}

        username = self._get_github_username()
        if not username:
            username = self._config_username

        if base_branch is None:
            base_branch = self.default_branch
        if head_branch is None:
            head_branch = "feature/init"

        step_info = {
            "base_branch": base_branch,
            "head_branch": head_branch,
            "title": title
        }

        git_dir = dir_path / ".git"
        git_exists = git_dir.exists()

        if force_clean and git_exists:
            try:
                import shutil
                shutil.rmtree(git_dir)
                steps.append("强制清理本地git: 成功")
                git_exists = False
            except Exception as e:
                steps.append(f"强制清理本地git: 失败 ({e})")
                return {
                    "success": False,
                    "error": f"无法强制清理本地.git目录: {e}",
                    "suggestion": "请手动删除 .git 目录后重试，或者不使用 --force 选项",
                    "steps": steps,
                    "step_info": step_info
                }

        create_result = self.create_repository(directory_path)
        results["create_repo"] = create_result
        steps.append(f"创建仓库: {'成功' if create_result['success'] else '失败'}")
        
        if not create_result["success"]:
            error_lower = create_result.get("error", "").lower()
            if "already exists" not in error_lower and "已存在" not in error_lower:
                return {
                    "success": False,
                    "error": f"创建仓库失败: {create_result['error']}",
                    "steps": steps,
                    "results": results,
                    "step_info": step_info
                }

        branch_status = self._check_branches(dir_path, base_branch, head_branch)
        steps.append(f"检查分支状态: {branch_status['status']}")
        
        if branch_status["need_init"]:
            init_commit_msg = f"初始化: {title}"
            init_commit_result = self._auto_commit_and_push(
                dir_path, 
                base_branch, 
                init_commit_msg, 
                is_initial=True
            )
            results["init_commit"] = init_commit_result
            steps.append(f"初始化提交 ({base_branch}): {'成功' if init_commit_result['success'] else '失败'}")
            
            if not init_commit_result["success"]:
                return {
                    "success": False,
                    "error": f"初始化提交失败: {init_commit_result.get('error', '未知错误')}",
                    "steps": steps,
                    "results": results,
                    "step_info": step_info
                }
        else:
            steps.append(f"跳过初始化提交: {branch_status.get('reason', '已有基础分支')}")

        if branch_status["need_head_branch"] or not branch_status["head_has_commits"]:
            feature_commit_msg = f"功能: {title}"
            feature_commit_result = self._auto_commit_and_push(
                dir_path, 
                head_branch, 
                feature_commit_msg, 
                is_initial=False,
                base_branch=base_branch
            )
            results["feature_commit"] = feature_commit_result
            steps.append(f"功能提交 ({head_branch}): {'成功' if feature_commit_result['success'] else '失败'}")
            
            if not feature_commit_result["success"]:
                return {
                    "success": False,
                    "error": f"功能提交失败: {feature_commit_result.get('error', '未知错误')}",
                    "steps": steps,
                    "results": results,
                    "step_info": step_info
                }
        else:
            steps.append(f"跳过功能提交: 源分支已存在且有提交")

        pr_result = self.create_pull_request(
            directory_path, 
            title, 
            head_branch=head_branch, 
            base_branch=base_branch
        )
        results["create_pr"] = pr_result
        steps.append(f"创建PR: {'成功' if pr_result['success'] else '失败'}")
        
        if not pr_result["success"]:
            return {
                "success": False,
                "error": f"创建PR失败: {pr_result.get('error', '未知错误')}",
                "steps": steps,
                "results": results,
                "step_info": step_info,
                "branch_status": branch_status
            }

        result = {
            "success": True,
            "repo_name": repo_name,
            "repo_url": create_result.get("repo_url") or f"https://github.com/{username}/{repo_name}",
            "pr_number": pr_result["pr_number"],
            "pr_title": pr_result["pr_title"],
            "pr_url": pr_result["pr_url"],
            "pr_state": pr_result["pr_state"],
            "username": username,
            "step_info": step_info,
            "branch_status": branch_status,
            "steps": steps,
            "results": results,
            "message": f"自动PR流程完成: {head_branch} -> {base_branch}"
        }

        if merge:
            merge_result = self.merge_pull_request(directory_path, pr_result["pr_number"], merge_method)
            results["merge"] = merge_result
            steps.append(f"合并PR: {'成功' if merge_result['success'] else '失败'}")
            result["merge_result"] = merge_result
            
            if merge_result["success"]:
                result["message"] += " -> PR合并"
            else:
                result["merge_error"] = merge_result.get("error")
                result["message"] += " -> PR合并失败"

        return result

    def _check_branches(self, dir_path: Path, base_branch: str, head_branch: str):
        git_dir = dir_path / ".git"
        if not git_dir.exists():
            return {
                "status": "无git仓库",
                "need_init": True,
                "need_head_branch": True,
                "base_has_commits": False,
                "head_has_commits": False
            }

        branches_result = self._run_git_command(["branch", "-a"], cwd=str(dir_path))
        branches_output = branches_result.get("output", "") if branches_result["success"] else ""
        
        base_exists = base_branch in branches_output
        head_exists = head_branch in branches_output
        
        base_has_commits = False
        head_has_commits = False
        
        if base_exists:
            log_result = self._run_git_command(["log", "-n", "1", base_branch], cwd=str(dir_path))
            base_has_commits = log_result["success"]
        
        if head_exists:
            log_result = self._run_git_command(["log", "-n", "1", head_branch], cwd=str(dir_path))
            head_has_commits = log_result["success"]
        
        return {
            "status": "已有git仓库",
            "need_init": not base_has_commits,
            "need_head_branch": not head_exists or not head_has_commits,
            "base_exists": base_exists,
            "head_exists": head_exists,
            "base_has_commits": base_has_commits,
            "head_has_commits": head_has_commits,
            "reason": f"基础分支({base_branch}): {'有提交' if base_has_commits else '无提交'}, 源分支({head_branch}): {'有提交' if head_has_commits else '无提交'}"
        }

    def _auto_commit_and_push(self, dir_path: Path, branch_name: str, 
                               commit_message: str, is_initial: bool = False,
                               base_branch: str = None):
        try:
            if is_initial:
                init_result = self._run_git_command(["init"], cwd=str(dir_path))
                if not init_result["success"] and "already exists" not in init_result["error"]:
                    return {"success": False, "error": f"git init失败: {init_result['error']}"}

            current_branch_result = self._run_git_command(["branch", "--show-current"], cwd=str(dir_path))
            current_branch = current_branch_result["output"] if current_branch_result["success"] else None

            if is_initial or not current_branch:
                checkout_result = self._run_git_command(["checkout", "-b", branch_name], cwd=str(dir_path))
                if not checkout_result["success"]:
                    return {"success": False, "error": f"创建分支失败: {checkout_result['error']}"}
            else:
                if base_branch:
                    checkout_base_result = self._run_git_command(["checkout", base_branch], cwd=str(dir_path))
                    if not checkout_base_result["success"]:
                        return {"success": False, "error": f"切换到基础分支失败: {checkout_base_result['error']}"}

                branch_exists_result = self._run_git_command(["branch", "-a"], cwd=str(dir_path))
                if branch_exists_result["success"] and branch_name in branch_exists_result["output"]:
                    checkout_result = self._run_git_command(["checkout", branch_name], cwd=str(dir_path))
                    if not checkout_result["success"]:
                        return {"success": False, "error": f"切换分支失败: {checkout_result['error']}"}
                else:
                    checkout_result = self._run_git_command(["checkout", "-b", branch_name], cwd=str(dir_path))
                    if not checkout_result["success"]:
                        return {"success": False, "error": f"创建分支失败: {checkout_result['error']}"}

            timestamp_file = dir_path / f".gitpr_{branch_name.replace('/', '_')}_marker.txt"
            timestamp_content = f"Branch: {branch_name}\nCommit: {commit_message}\nTime: {os.popen('date /t').read().strip()} {os.popen('time /t').read().strip()}"
            
            try:
                with open(timestamp_file, 'w', encoding='utf-8') as f:
                    f.write(timestamp_content)
            except Exception as e:
                return {"success": False, "error": f"创建标记文件失败: {e}"}

            add_result = self._run_git_command(["add", "."], cwd=str(dir_path))
            if not add_result["success"]:
                return {"success": False, "error": f"添加文件失败: {add_result['error']}"}

            commit_result = self._run_git_command(
                ["commit", "-m", commit_message],
                cwd=str(dir_path)
            )
            
            if not commit_result["success"]:
                if "nothing to commit" in commit_result["error"] or "nothing added to commit" in commit_result["error"]:
                    readme_file = dir_path / "README.md"
                    readme_content = f"# {dir_path.name}\n\n自动创建: {commit_message}\n"
                    try:
                        with open(readme_file, 'w', encoding='utf-8') as f:
                            f.write(readme_content)
                    except:
                        pass
                    
                    add_result2 = self._run_git_command(["add", "."], cwd=str(dir_path))
                    if add_result2["success"]:
                        commit_result2 = self._run_git_command(
                            ["commit", "-m", commit_message],
                            cwd=str(dir_path)
                        )
                        if commit_result2["success"]:
                            commit_result = commit_result2
            
            if not commit_result["success"]:
                if "nothing to commit" in commit_result["error"] or "nothing added to commit" in commit_result["error"]:
                    return {
                        "success": True,
                        "message": "没有需要提交的更改",
                        "branch": branch_name
                    }
                return {"success": False, "error": f"提交失败: {commit_result['error']}"}

            push_result = self._run_git_command(
                ["push", "-u", "origin", branch_name],
                cwd=str(dir_path)
            )
            
            if not push_result["success"]:
                return {"success": False, "error": f"推送失败: {push_result['error']}"}

            return {
                "success": True,
                "message": f"提交并推送成功: {commit_message}",
                "branch": branch_name,
                "commit_message": commit_message
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
