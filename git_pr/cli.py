import json
import click
from pathlib import Path
from .config import ConfigManager
from .github_api import GitHubAPI


def print_json(result):
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@click.group()
@click.pass_context
def cli(ctx):
    """GitHub PR CLI Tool - 用于管理GitHub仓库和Pull Request"""
    ctx.ensure_object(dict)
    ctx.obj['config'] = ConfigManager()
    ctx.obj['api'] = GitHubAPI(ctx.obj['config'])


@cli.command()
@click.option('--token', prompt=True, hide_input=True, help='GitHub Personal Access Token')
@click.option('--username', prompt=True, help='GitHub用户名')
@click.option('--branch', default='main', help='默认分支名')
@click.pass_context
def config(ctx, token, username, branch):
    """配置GitHub相关信息（TOKEN加密保存）"""
    config_manager = ctx.obj['config']
    config_manager.set_github_token(token)
    config_manager.set_github_username(username)
    config_manager.set_default_branch(branch)
    
    result = {
        "success": True,
        "message": "配置已保存",
        "username": username,
        "default_branch": branch,
        "token_encrypted": True
    }
    print_json(result)


@cli.command()
@click.pass_context
def status(ctx):
    """查看当前配置状态"""
    config_manager = ctx.obj['config']
    result = {
        "success": True,
        "configured": config_manager.is_configured(),
        "username": config_manager.get_github_username(),
        "default_branch": config_manager.get_default_branch(),
        "token_set": bool(config_manager.get_github_token())
    }
    print_json(result)


@cli.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.pass_context
def create_repo(ctx, directory):
    """创建新的GitHub仓库（参数为目录路径，取最后一个目录名作为仓库名）"""
    api = ctx.obj['api']
    result = api.create_repository(directory)
    print_json(result)


@cli.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('title')
@click.pass_context
def commit(ctx, directory, title):
    """提交代码到远程仓库（参数：目录路径，TITLE）"""
    api = ctx.obj['api']
    result = api.commit_and_push(directory, title)
    print_json(result)


@cli.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('title')
@click.option('--head', default=None, help='源分支名')
@click.option('--base', default=None, help='目标分支名')
@click.pass_context
def create_pr(ctx, directory, title, head, base):
    """创建Pull Request（参数：目录路径，TITLE）"""
    api = ctx.obj['api']
    result = api.create_pull_request(directory, title, head, base)
    print_json(result)


@cli.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('pr_number', type=int)
@click.option('--method', type=click.Choice(['merge', 'squash', 'rebase']), default='merge',
              help='合并方式: merge(合并), squash(压缩), rebase(变基)')
@click.pass_context
def merge(ctx, directory, pr_number, method):
    """合并Pull Request（参数：目录路径，PR编号）"""
    api = ctx.obj['api']
    result = api.merge_pull_request(directory, pr_number, method)
    print_json(result)


@cli.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('title')
@click.option('--merge', is_flag=True, help='创建PR后自动合并')
@click.pass_context
def full(ctx, directory, title, merge):
    """完整工作流：创建仓库 -> 提交代码 -> 创建PR -> 可选合并（参数：目录路径，TITLE）"""
    api = ctx.obj['api']
    result = api.full_workflow(directory, title, merge)
    print_json(result)


if __name__ == '__main__':
    cli()
