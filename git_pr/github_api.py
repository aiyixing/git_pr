import os
import subprocess
from pathlib import Path
from github import Github, GithubException
from .config import ConfigManager


class GitHubAPI:
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.token = self.config.get_github_token()
        self.username = self.config.get_github_username()
        self.default_branch = self.config.get_default_branch()
        self.g = Github(self.token) if self.token else None

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
                "output": result.stdout,
                "error": result.stderr
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "output": e.stdout,
                "error": e.stderr
            }

    def create_repository(self, directory_path: str):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        if not self.g:
            return {
                "success": False,
                "error": "GitHub not configured. Please run 'gitpr config' first.",
                "repo_name": repo_name
            }

        try:
            user = self.g.get_user()
            repo = user.create_repo(repo_name, private=False)
            
            if not (dir_path / ".git").exists():
                self._run_git_command(["init"], cwd=str(dir_path))
            
            self._run_git_command(
                ["remote", "add", "origin", repo.clone_url],
                cwd=str(dir_path)
            )

            return {
                "success": True,
                "repo_name": repo_name,
                "repo_url": repo.html_url,
                "clone_url": repo.clone_url,
                "message": f"Repository '{repo_name}' created successfully"
            }
        except GithubException as e:
            return {
                "success": False,
                "error": f"GitHub API error: {e.data.get('message', str(e))}",
                "repo_name": repo_name
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "repo_name": repo_name
            }

    def commit_and_push(self, directory_path: str, commit_message: str):
        dir_path = Path(directory_path).resolve()

        if not (dir_path / ".git").exists():
            return {
                "success": False,
                "error": "Not a git repository. Please initialize first."
            }

        add_result = self._run_git_command(["add", "."], cwd=str(dir_path))
        if not add_result["success"]:
            return {
                "success": False,
                "error": f"Failed to add files: {add_result['error']}"
            }

        commit_result = self._run_git_command(
            ["commit", "-m", commit_message],
            cwd=str(dir_path)
        )
        if not commit_result["success"]:
            if "nothing to commit" in commit_result["error"]:
                return {
                    "success": True,
                    "message": "Nothing to commit, working tree clean",
                    "commit_message": commit_message
                }
            return {
                "success": False,
                "error": f"Failed to commit: {commit_result['error']}"
            }

        push_result = self._run_git_command(
            ["push", "-u", "origin", self.default_branch],
            cwd=str(dir_path)
        )
        if not push_result["success"]:
            return {
                "success": False,
                "error": f"Failed to push: {push_result['error']}"
            }

        return {
            "success": True,
            "message": f"Committed and pushed successfully: {commit_message}",
            "commit_message": commit_message
        }

    def create_pull_request(self, directory_path: str, title: str, head_branch: str = None, base_branch: str = None):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        if head_branch is None:
            head_branch = self.default_branch
        if base_branch is None:
            base_branch = self.default_branch

        if not self.g:
            return {
                "success": False,
                "error": "GitHub not configured. Please run 'gitpr config' first."
            }

        try:
            repo = self.g.get_repo(f"{self.username}/{repo_name}")
            
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
                "message": f"Pull request created successfully: #{pr.number}"
            }
        except GithubException as e:
            return {
                "success": False,
                "error": f"GitHub API error: {e.data.get('message', str(e))}",
                "repo_name": repo_name
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
                "error": "GitHub not configured. Please run 'gitpr config' first."
            }

        try:
            repo = self.g.get_repo(f"{self.username}/{repo_name}")
            pr = repo.get_pull(pr_number)

            if not pr.mergeable:
                return {
                    "success": False,
                    "error": f"Pull request #{pr_number} is not mergeable",
                    "pr_number": pr_number
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
                "message": f"Pull request #{pr_number} merged successfully"
            }
        except GithubException as e:
            return {
                "success": False,
                "error": f"GitHub API error: {e.data.get('message', str(e))}",
                "pr_number": pr_number
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "pr_number": pr_number
            }

    def full_workflow(self, directory_path: str, title: str, merge: bool = False):
        dir_path = Path(directory_path).resolve()
        repo_name = dir_path.name

        create_result = self.create_repository(directory_path)
        if not create_result["success"] and "already exists" not in create_result.get("error", ""):
            return create_result

        commit_result = self.commit_and_push(directory_path, title)
        if not commit_result["success"]:
            return commit_result

        pr_result = self.create_pull_request(directory_path, title)
        if not pr_result["success"]:
            return {
                "success": False,
                "error": f"Failed to create PR: {pr_result.get('error', 'Unknown error')}",
                "commit_result": commit_result
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
            "message": "Full workflow completed: repo created, committed, pushed, and PR created"
        }

        if merge:
            merge_result = self.merge_pull_request(directory_path, pr_result["pr_number"])
            result["merge_result"] = merge_result
            if merge_result["success"]:
                result["message"] += " and merged"
            else:
                result["merge_error"] = merge_result.get("error")

        return result
