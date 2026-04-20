from setuptools import setup, find_packages

setup(
    name="gitpr",
    version="1.0.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click>=8.0.0",
        "pygithub>=1.59.0",
        "cryptography>=41.0.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "gitpr=git_pr.cli:cli",
        ],
    },
    author="GitPR CLI",
    description="GitHub PR CLI Tool - 用于管理GitHub仓库和Pull Request",
    python_requires=">=3.8",
)
