import json
import click
from pathlib import Path
from .config import ConfigManager
from .github_api import GitHubAPI


def print_json(result):
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.pass_context
def cli(ctx):
    """
    GitHub PR CLI 工具 - 用于管理GitHub仓库和Pull Request
    
    所有命令均返回JSON格式数据。
    
    使用前请先配置GitHub信息: gitpr config
    """
    ctx.ensure_object(dict)
    ctx.obj['config'] = ConfigManager()
    ctx.obj['api'] = GitHubAPI(ctx.obj['config'])


@cli.command('config', context_settings=CONTEXT_SETTINGS)
@click.option('--token', default=None, 
              hide_input=True, 
              help='GitHub Personal Access Token (需要repo权限)')
@click.option('--username', default=None, 
              help='GitHub用户名')
@click.option('--branch', default=None, 
              help='默认分支名')
@click.pass_context
def config_cmd(ctx, token, username, branch):
    """
    配置GitHub相关信息（TOKEN加密保存）
    
    修改配置时，只需要提供要修改的参数，未提供的参数保留原有值。
    
    \b
    参数说明:
      --token     GitHub Personal Access Token
      --username  GitHub用户名
      --branch    默认分支名
    
    \b
    使用示例:
      # 首次配置所有参数
      gitpr config --token ghp_xxxxxxxxxxxx --username myname --branch main
      
      # 只修改默认分支
      gitpr config --branch master
      
      # 只修改用户名
      gitpr config --username newname
    
    \b
    返回JSON示例:
      {
        "success": true,
        "message": "配置已保存",
        "username": "myname",
        "default_branch": "main",
        "token_encrypted": true
      }
    """
    config_manager = ctx.obj['config']
    
    existing_token = config_manager.get_github_token()
    existing_username = config_manager.get_github_username()
    existing_branch = config_manager.get_default_branch()
    
    new_token = token if token is not None else existing_token
    new_username = username if username is not None else existing_username
    new_branch = branch if branch is not None else existing_branch
    
    if new_token:
        config_manager.set_github_token(new_token)
    if new_username:
        config_manager.set_github_username(new_username)
    if new_branch:
        config_manager.set_default_branch(new_branch)
    
    result = {
        "success": True,
        "message": "配置已保存",
        "username": new_username,
        "default_branch": new_branch,
        "token_encrypted": bool(new_token),
        "changes": {
            "token": token is not None,
            "username": username is not None,
            "branch": branch is not None
        }
    }
    print_json(result)


@cli.command('status', context_settings=CONTEXT_SETTINGS)
@click.pass_context
def status_cmd(ctx):
    """
    查看当前配置状态
    
    检查GitHub配置是否完整。
    
    \b
    使用示例:
      gitpr status
    
    \b
    返回JSON示例:
      {
        "success": true,
        "configured": true,
        "config_username": "your_username",
        "token_username": "actual_username",
        "default_branch": "main",
        "token_set": true,
        "token_valid": true
      }
    """
    config_manager = ctx.obj['config']
    api = ctx.obj['api']
    
    config_username = config_manager.get_github_username()
    token_set = bool(config_manager.get_github_token())
    
    token_username = None
    token_valid = False
    
    if token_set:
        github_user = api._get_github_user()
        if github_user:
            token_valid = True
            token_username = github_user.login
    
    result = {
        "success": True,
        "configured": config_manager.is_configured(),
        "config_username": config_username,
        "token_username": token_username,
        "default_branch": config_manager.get_default_branch(),
        "token_set": token_set,
        "token_valid": token_valid
    }
    
    print_json(result)


@cli.command('create-repo', context_settings=CONTEXT_SETTINGS)
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.pass_context
def create_repo_cmd(ctx, directory):
    """
    创建新的GitHub仓库
    
    参数为本地目录路径，自动取路径的最后一个目录名作为GitHub仓库名。
    如果本地目录尚未初始化git，会自动执行git init。
    
    \b
    参数说明:
      DIRECTORY  本地目录的绝对路径或相对路径
                 仓库名 = 路径的最后一个目录名
                 例如: /path/to/myproject -> 仓库名: myproject
    
    \b
    使用示例:
      # 使用绝对路径
      gitpr create-repo C:\\projects\\myproject
      
      # 使用相对路径（当前目录下的myproject文件夹）
      gitpr create-repo ./myproject
      
      # 使用当前目录
      gitpr create-repo .
    
    \b
    执行流程:
      1. 在GitHub上创建远程仓库
      2. 如果本地目录没有.git，则执行git init
      3. 添加远程origin指向新创建的GitHub仓库
    
    \b
    返回JSON示例 (成功):
      {
        "success": true,
        "repo_name": "myproject",
        "repo_url": "https://github.com/myname/myproject",
        "clone_url": "https://github.com/myname/myproject.git",
        "message": "Repository 'myproject' created successfully"
      }
    
    \b
    返回JSON示例 (失败):
      {
        "success": false,
        "error": "GitHub API error: Repository creation failed",
        "repo_name": "myproject"
      }
    """
    api = ctx.obj['api']
    result = api.create_repository(directory)
    print_json(result)


@cli.command('commit', context_settings=CONTEXT_SETTINGS)
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('title')
@click.pass_context
def commit_cmd(ctx, directory, title):
    """
    提交代码到远程GitHub仓库
    
    执行 git add . -> git commit -> git push 完整流程。
    TITLE参数作为commit message。
    
    \b
    参数说明:
      DIRECTORY  本地git仓库目录路径
      TITLE      提交信息（commit message）
                 建议格式: "feat: 添加新功能" 或 "fix: 修复bug"
    
    \b
    使用示例:
      # 提交当前目录的所有更改
      gitpr commit . "feat: 添加用户登录功能"
      
      # 提交指定目录
      gitpr commit C:\\projects\\myproject "fix: 修复登录页面样式问题"
      
      # 使用英文提交信息
      gitpr commit ./myproject "initial commit"
    
    \b
    执行流程:
      1. git add . - 添加所有更改的文件
      2. git commit -m "TITLE" - 提交更改
      3. git push -u origin main - 推送到远程仓库
    
    \b
    返回JSON示例 (成功):
      {
        "success": true,
        "message": "Committed and pushed successfully: feat: 添加用户登录功能",
        "commit_message": "feat: 添加用户登录功能"
      }
    
    \b
    返回JSON示例 (无更改):
      {
        "success": true,
        "message": "Nothing to commit, working tree clean",
        "commit_message": "feat: 添加用户登录功能"
      }
    """
    api = ctx.obj['api']
    result = api.commit_and_push(directory, title)
    print_json(result)


@cli.command('create-pr', context_settings=CONTEXT_SETTINGS)
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('title')
@click.option('--head', default=None, 
              help='源分支名 (默认: 配置的默认分支，如main)')
@click.option('--base', default=None, 
              help='目标分支名 (默认: 配置的默认分支，如main)')
@click.pass_context
def create_pr_cmd(ctx, directory, title, head, base):
    """
    创建Pull Request
    
    在GitHub上创建一个新的Pull Request。
    TITLE参数作为PR的标题。
    
    \b
    参数说明:
      DIRECTORY  本地git仓库目录路径（用于确定仓库名）
      TITLE      Pull Request的标题
      --head     源分支名，即包含更改的分支 (默认: main)
      --base     目标分支名，即要合并到的分支 (默认: main)
    
    \b
    使用示例:
      # 在main分支上创建PR（从main到main，通常用于自动化流程）
      gitpr create-pr . "feat: 添加用户登录功能"
      
      # 从develop分支合并到main分支
      gitpr create-pr C:\\projects\\myproject "新功能发布" --head develop --base main
      
      # 从feature分支合并到develop
      gitpr create-pr ./myproject "添加支付模块" --head feature/payment --base develop
    
    \b
    返回JSON示例 (成功):
      {
        "success": true,
        "pr_number": 1,
        "pr_title": "feat: 添加用户登录功能",
        "pr_url": "https://github.com/myname/myproject/pull/1",
        "pr_state": "open",
        "message": "Pull request created successfully: #1"
      }
    
    \b
    返回JSON示例 (失败):
      {
        "success": false,
        "error": "GitHub API error: No commits between main and main",
        "repo_name": "myproject"
      }
    """
    api = ctx.obj['api']
    result = api.create_pull_request(directory, title, head, base)
    print_json(result)


@cli.command('merge', context_settings=CONTEXT_SETTINGS)
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('pr_number', type=int)
@click.option('--method', type=click.Choice(['merge', 'squash', 'rebase']), 
              default='merge',
              help='合并方式: merge(创建合并提交), squash(压缩为单个提交), rebase(变基)')
@click.pass_context
def merge_cmd(ctx, directory, pr_number, method):
    """
    合并Pull Request
    
    合并指定编号的Pull Request。支持三种合并方式。
    
    \b
    参数说明:
      DIRECTORY  本地git仓库目录路径（用于确定仓库名）
      PR_NUMBER  Pull Request的编号（数字）
      --method   合并方式:
                 - merge: 创建一个合并提交（保留所有提交历史）
                 - squash: 将所有提交压缩为单个提交
                 - rebase: 变基合并（线性历史）
    
    \b
    使用示例:
      # 合并编号为1的PR，使用默认merge方式
      gitpr merge . 1
      
      # 使用squash方式合并
      gitpr merge C:\\projects\\myproject 5 --method squash
      
      # 使用rebase方式合并
      gitpr merge ./myproject 3 --method rebase
    
    \b
    合并方式对比:
      merge:   保留完整的分支历史，适合大型项目
      squash:  简洁的提交历史，适合功能分支合并
      rebase:  线性历史，最简洁，但会修改提交记录
    
    \b
    返回JSON示例 (成功):
      {
        "success": true,
        "pr_number": 1,
        "pr_title": "feat: 添加用户登录功能",
        "pr_url": "https://github.com/myname/myproject/pull/1",
        "merged": true,
        "sha": "a1b2c3d4e5f6...",
        "message": "Pull request #1 merged successfully"
      }
    
    \b
    返回JSON示例 (失败 - 不可合并):
      {
        "success": false,
        "error": "Pull request #1 is not mergeable",
        "pr_number": 1
      }
    """
    api = ctx.obj['api']
    result = api.merge_pull_request(directory, pr_number, method)
    print_json(result)


@cli.command('full', context_settings=CONTEXT_SETTINGS)
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('title')
@click.option('--merge', is_flag=True, 
              help='创建PR后自动合并 (默认: false)')
@click.option('--method', type=click.Choice(['merge', 'squash', 'rebase']), 
              default='merge',
              help='合并方式，仅在--merge时有效 (默认: merge)')
@click.pass_context
def full_cmd(ctx, directory, title, merge, method):
    """
    完整工作流：创建仓库 -> 提交代码 -> 创建PR -> 可选合并
    
    一条命令完成从本地目录到GitHub PR的完整流程。
    这是最常用的命令，适合快速发布新项目或新功能。
    
    \b
    参数说明:
      DIRECTORY  本地目录路径
      TITLE      统一标题，同时用于:
                 - commit message
                 - PR标题
      --merge    添加此标志后，创建PR后会自动合并
      --method   合并方式 (merge/squash/rebase)，仅在--merge时有效
    
    \b
    使用示例:
      # 基础流程：创建仓库 -> 提交 -> 创建PR
      gitpr full C:\\projects\\myproject "初始化项目"
      
      # 完整流程：创建仓库 -> 提交 -> 创建PR -> 自动合并
      gitpr full . "新功能发布" --merge
      
      # 完整流程 + squash合并
      gitpr full ./myproject "修复紧急bug" --merge --method squash
    
    \b
    执行流程:
      1. 创建GitHub远程仓库（如果不存在）
      2. 初始化本地git（如果需要）
      3. git add . -> git commit -> git push
      4. 创建Pull Request
      5. 如果使用了--merge，则自动合并PR
    
    \b
    返回JSON示例 (无--merge):
      {
        "success": true,
        "repo_name": "myproject",
        "repo_url": "https://github.com/myname/myproject",
        "commit_message": "初始化项目",
        "pr_number": 1,
        "pr_title": "初始化项目",
        "pr_url": "https://github.com/myname/myproject/pull/1",
        "pr_state": "open",
        "message": "Full workflow completed: repo created, committed, pushed, and PR created"
      }
    
    \b
    返回JSON示例 (带--merge):
      {
        "success": true,
        "repo_name": "myproject",
        "repo_url": "https://github.com/myname/myproject",
        "commit_message": "初始化项目",
        "pr_number": 1,
        "pr_title": "初始化项目",
        "pr_url": "https://github.com/myname/myproject/pull/1",
        "pr_state": "open",
        "message": "Full workflow completed... and merged",
        "merge_result": {
          "success": true,
          "pr_number": 1,
          "merged": true,
          "sha": "a1b2c3d..."
        }
      }
    """
    api = ctx.obj['api']
    result = api.full_workflow(directory, title, merge, method)
    print_json(result)


@cli.command('delete-repo', context_settings=CONTEXT_SETTINGS)
@click.argument('repo_name')
@click.pass_context
def delete_repo_cmd(ctx, repo_name):
    """
    删除GitHub远程仓库
    
    \b
    参数说明:
      REPO_NAME  仓库名（不是完整路径，只是目录名）
    
    \b
    使用示例:
      # 删除名为comments的仓库
      gitpr delete-repo comments
    
    \b
    返回JSON示例:
      {
        "success": true,
        "repo_name": "comments",
        "username": "myname",
        "message": "仓库 'myname/comments' 已成功删除"
      }
    """
    api = ctx.obj['api']
    result = api.delete_repository(repo_name)
    print_json(result)


@cli.command('auto-pr', context_settings=CONTEXT_SETTINGS)
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('title')
@click.option('--base', 'base_branch', default=None, 
              help='目标分支名（默认: 配置的默认分支）')
@click.option('--head', 'head_branch', default=None, 
              help='源分支名（默认: feature/init）')
@click.option('--merge', is_flag=True, default=False,
              help='创建PR后自动合并')
@click.option('--method', 'merge_method', 
              type=click.Choice(['merge', 'squash', 'rebase']), 
              default='merge',
              help='合并方式 (merge/squash/rebase)')
@click.option('--force', 'force_clean', is_flag=True, default=False,
              help='强制清理本地.git目录（谨慎使用！会删除所有git历史）')
@click.pass_context
def auto_pr_cmd(ctx, directory, title, base_branch, head_branch, merge, merge_method, force_clean):
    """
    自动完成完整PR流程（一条命令搞定）
    
    这个命令会自动完成所有步骤，确保最终能创建一个PR。
    它会自动创建两个不同的分支，分别提交不同的内容，然后创建PR。
    
    注意：默认不会删除现有的.git目录，而是智能检查现有分支状态。
    如果需要完全重新开始，可以使用 --force 选项。
    
    \b
    参数说明:
      DIRECTORY   本地目录路径
      TITLE       标题，用于commit message和PR标题
      --base      目标分支名（默认: 配置的默认分支，如master/main）
      --head      源分支名（默认: feature/init）
      --merge     添加此标志后，创建PR后会自动合并
      --method    合并方式 (merge/squash/rebase)，仅在--merge时有效
      --force     强制清理本地.git目录（谨慎使用！会删除所有git历史）
    
    \b
    使用示例:
      # 基础使用（智能检查现有状态）
      gitpr auto-pr C:\\projects\\myproject "初始化项目"
      
      # 指定分支
      gitpr auto-pr C:\\projects\\myproject "新功能" --base master --head develop
      
      # 创建PR后自动合并
      gitpr auto-pr . "快速发布" --merge
      
      # 强制完全重新开始（删除现有.git）
      gitpr auto-pr . "重新初始化" --force
      
      # 使用squash合并
      gitpr auto-pr . "修复bug" --merge --method squash
    
    \b
    自动执行流程:
      1. 检查现有.git目录（--force时才删除）
      2. 创建GitHub远程仓库
      3. 检查现有分支状态
      4. 如果没有基础分支，在目标分支（如master）上做第一次提交
      5. 如果没有源分支，创建源分支（如feature/init）
      6. 在源分支上做第二次提交（创建标记文件确保有差异）
      7. 推送两个分支到远程
      8. 创建Pull Request: 源分支 -> 目标分支
      9. 如果使用了--merge，则自动合并PR
    
    \b
    返回JSON示例:
      {
        "success": true,
        "repo_name": "myproject",
        "repo_url": "https://github.com/myname/myproject",
        "pr_number": 1,
        "pr_title": "初始化项目",
        "pr_url": "https://github.com/myname/myproject/pull/1",
        "pr_state": "open",
        "step_info": {
          "base_branch": "master",
          "head_branch": "feature/init",
          "title": "初始化项目"
        },
        "branch_status": {
          "status": "已有git仓库",
          "base_has_commits": true,
          "head_has_commits": false
        },
        "steps": [
          "创建仓库: 成功",
          "检查分支状态: 已有git仓库",
          "跳过初始化提交: 已有基础分支",
          "功能提交 (feature/init): 成功",
          "创建PR: 成功"
        ],
        "message": "自动PR流程完成: feature/init -> master"
      }
    """
    api = ctx.obj['api']
    result = api.auto_pr_workflow(
        directory, 
        title, 
        base_branch=base_branch,
        head_branch=head_branch,
        merge=merge,
        merge_method=merge_method,
        force_clean=force_clean
    )
    print_json(result)


if __name__ == '__main__':
    cli()
