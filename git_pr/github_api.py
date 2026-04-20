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
        self._username = self.config.get_github_username()
        self.default_branch = self.config.get_default_branch()
        self.g = Github(self.token) if self.token else None
        self._github_user = None

    @property
    def username(self):
        if self._github_user:
            return self._github_user.login
        return self._username

    def _get_github_user(self):
        if self._github_user:
            return self._github_user
        if self.g:
            try:
                self._github_user = self.g.get_user()
                return self._github_user
            except:
                pass
        return None

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

    def _parse_remote_url(self, remote_url: str):
        patterns = [
            r'^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$',
            r'^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$',
            r'^ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?$',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, remote_url)
            if match:
                return {
                    "username": match.group(1),
                    "repo_name": match.group(2)
                }
        return None

    def _get_username_from_remote(self, dir_path: Path):
        remote_result = self._run_git_command(["remote", "get-url", "origin"], cwd=str(dir_path))
        if remote_result["success"] and remote_result["output"]:
            parsed = self._parse_remote_url(remote_result["output"])
            if parsed:
                return parsed["username"]
        return None

    def _detect_username(self, dir_path: Path = None):
        github_user = self._get_github_user()
        if github_user:
            return github_user.login
        
        if dir_path:
            remote_username = self._get_username_from_remote(dir_path)
            if remote_username:
                return remote_username
        
        if self._username and "@" not in self._username:
            return self._username
        
        return None

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

    def _check_remote_repo_exists(self, repo_name: str, dir_path: Path = None):
        username = self._detect_username(dir_path)
        
        if not username:
            return {
                "exists": False,
                "error": "无法确定GitHub用户名。",
                "suggestion": "请确保TOKEN有效，或者检查git remote配置。",
                "detected_info": {
                    "config_username": self._username,
                    "from_token": bool(self._get_github_user()),
                    "from_remote": bool(self._get_username_from_remote(dir_path) if dir_path else None)
                }
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
                remote_username = self._get_username_from_remote(dir_path) if dir_path else None
                suggestion_parts = []
                
                if self._username and "@" in self._username:
                    suggestion_parts.append(f"注意: 配置的用户名 '{self._username}' 看起来是邮箱，GitHub用户名不应包含@符号。")
                
                if remote_username and remote_username != username:
                    suggestion_parts.append(f"从remote检测到的用户名: {remote_username}")
                
                suggestion_parts.append(f"请执行 'gitpr config' 重新配置正确的用户名。")
                suggestion_parts.append(f"或者手动检查: git remote -v")
                
                return {
                    "exists": False,
                    "error": f"远程仓库 '{username}/{repo_name}' 不存在。",
                    "suggestion": "\n".join(suggestion_parts),
                    "username": username,
                    "repo_name": repo_name,
                    "detected_info": {
                        "config_username": self._username,
                        "token_username": self._get_github_user().login if self._get_github_user() else None,
                        "remote_username": remote_username
                    }
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

        github_user = self._get_github_user()
        if not github_user:
            return {
                "success": False,
                "error": "无法通过TOKEN获取GitHub用户信息。",
                "suggestion": "请检查TOKEN是否有效，需要repo权限。",
                "repo_name": repo_name
            }

        try:
            repo = github_user.create_repo(repo_name, private=False)
            
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
                "username": github_user.login,
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
                    "username": github_user.login,
                    "suggestion": "如果本地目录未关联，请手动执行: git remote add origin <仓库地址>"
                }
            return {
                "success": False,
                "error": f"GitHub API错误: {error_msg}",
                "repo_name": repo_name,
                "username": github_user.login
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

        current_branch = self._get_current_branch(dir_path) or self.default_branch
        
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

        username = self._detect_username(dir_path)
        return {
            "success": True,
            "message": f"提交并推送成功: {commit_message}",
            "commit_message": commit_message,
            "branch": current_branch,
            "repo_name": repo_name,
            "username": username,
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

        repo_check = self._check_remote_repo_exists(repo_name, dir_path)
        if not repo_check["exists"]:
            return {
                "success": False,
                "error": repo_check["error"],
                "suggestion": repo_check.get("suggestion"),
                "repo_name": repo_name,
                "detected_info": repo_check.get("detected_info")
            }

        username = repo_check["username"]

        if head_branch is None:
            head_branch = self._get_current_branch(dir_path) or self.default_branch
        if base_branch is None:
            base_branch = self.default_branch

        try:
            repo = repo_check["repo"]
            
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
                "head_branch": head_branch,
                "base_branch": base_branch,
                "repo_name": repo_name,
                "username": username,
                "message": f"Pull request 创建成功: #{pr.number}",
                "next_step": f"可执行合并: gitpr merge {dir_path} {pr.number}"
            }
        except GithubException as e:
            error_msg = e.data.get('message', str(e))
            suggestion = ""
            
            if "No commits between" in error_msg:
                suggestion = f"源分支 '{head_branch}' 和目标分支 '{base_branch}' 之间没有差异。请确保有新的提交。"
            elif "A pull request already exists" in error_msg:
                suggestion = "已存在相同分支的Pull Request。请先关闭或合并现有的PR。"
            elif "Not Found" in error_msg:
                suggestion = f"请确保分支 '{head_branch}' 已推送到远程仓库。当前检测到的用户名: {username}"
            
            return {
                "success": False,
                "error": f"GitHub API错误: {error_msg}",
                "repo_name": repo_name,
                "username": username,
                "head_branch": head_branch,
                "base_branch": base_branch,
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

        repo_check = self._check_remote_repo_exists(repo_name, dir_path)
        if not repo_check["exists"]:
            return {
                "success": False,
                "error": repo_check["error"],
                "suggestion": repo_check.get("suggestion"),
                "pr_number": pr_number
            }

        username = repo_check["username"]

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
            "username": pr_result.get("username"),
            "steps": steps,
            "results": results,
            "message": "完整工作流完成: 仓库创建 -> 代码提交 -> PR创建"
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

        result["steps"] = steps
        return result
