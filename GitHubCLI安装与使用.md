# GitHub CLI 安装与使用 gh 创建仓库（SecondBrainOS）操作记录

本文档记录在本机（Linux/Ubuntu）为本项目安装 GitHub CLI（`gh`）并使用它在 GitHub 上创建远端仓库、绑定本地仓库并推送代码的完整过程。

## 1. 前置条件

- 已安装 Git（`git`）
- 能访问 GitHub（`github.com`）
- 具备 GitHub 账号
- 本项目工作目录：`/home/surdring/workspace/SecondBrainOS`

## 2. 初始化本地 Git 仓库

> 由于最初目录并不是 Git 仓库，先初始化。

### 2.1 检查仓库状态

```bash
git status
```

预期输出（示例）：

```text
fatal: 不是 git 仓库（或者直至挂载点 / 的任何父目录）
```

### 2.2 初始化并切换到 main 分支

```bash
git init
git branch -m main
```

说明：
- `git init`：初始化 `.git/`
- `git branch -m main`：将默认分支重命名为 `main`

## 3. 生成 .gitignore

在项目根目录创建 `.gitignore`，用于避免提交敏感信息或无关产物。

关键点：
- 忽略本地环境变量文件：`.env.local`、`.env`、`.env.*.local`
- 忽略 Python 虚拟环境：`.venv/`
- 忽略 Node 构建产物与依赖：`node_modules/`、`web/dist/`、`zip/dist/`

## 4. 首次提交（Initial commit）

```bash
git add .
git commit -m "Initial commit: SecondBrainOS - AI个性化记忆辅助系统\n\n- 完整需求与架构文档 (sbo.md)\n- 项目工程规范 (AGENTS.md)\n- 前端原型实现 (zip/)\n- 后端核心架构设计\n- 分层记忆系统：工作记忆/语义记忆/情景记忆\n- 支持本地 llama.cpp 和外部 PROVIDER LLM 配置\n- OpenClaw 可选集成方案\n- 独立 Web 应用形态设计"
```

说明：
- 提交信息包含本次初始化提交的主要内容摘要，便于后续追溯。

## 5. 安装 GitHub CLI（gh）

### 5.1 检查 gh 是否已安装

```bash
gh --version
```

若未安装，可能输出：

```text
找不到命令 “gh”
```

### 5.2 使用 apt 安装（Ubuntu）

```bash
sudo apt update && sudo apt install gh -y
```

备注：
- 执行 `apt update` 时如果出现某些第三方源 GPG 签名过期的 warning（例如 Warp 的 apt 源），通常 **不会阻止** 从 Ubuntu 官方源安装 `gh`；但建议后续清理或更新对应第三方源 key，避免未来更新受影响。

### 5.3 验证安装

```bash
gh --version
```

预期输出（示例）：

```text
gh version 2.45.0 ...
```

## 6. GitHub CLI 登录（gh auth login）

### 6.1 检查登录状态

```bash
gh auth status
```

若未登录，输出类似：

```text
You are not logged into any GitHub hosts. To log in, run: gh auth login
```

### 6.2 登录到 GitHub.com

```bash
gh auth login
```

交互建议：
- **Host**：选择 `GitHub.com`
- **Git operations protocol**：选择 `HTTPS`
- **Authentication**：选择通过浏览器登录（device code）

登录过程会显示：
- 一次性验证码（one-time code）
- 需要打开的 URL（`https://github.com/login/device`）

完成后会看到：

```text
✓ Authentication complete.
✓ Logged in as <your-username>
```

然后再次确认：

```bash
gh auth status
```

应显示已登录账号与 token scopes（示例：包含 `repo` 权限）。

## 7. 使用 gh 创建远端仓库并推送

### 7.1 创建 GitHub 仓库并推送当前目录

在项目根目录执行：

```bash
gh repo create SecondBrainOS \
  --public \
  --description "AI 个性化记忆辅助系统 - 智能数字外脑" \
  --source=. \
  --push
```

该命令会自动完成：
- 在 GitHub 创建 `surdring/SecondBrainOS`
- 自动添加远端 `origin`
- 将本地 `main` 推送到远端并设置 upstream

成功输出示例要点：

```text
✓ Created repository <owner>/SecondBrainOS on GitHub
✓ Added remote https://github.com/<owner>/SecondBrainOS.git
✓ Pushed commits ...
```

### 7.2 验证远端仓库

打开浏览器访问：

- https://github.com/surdring/SecondBrainOS

## 8. 常见问题与建议

### 8.1 为什么建议使用 GitHub CLI？

- **减少手工步骤**：创建仓库、设置 remote、推送一次性完成
- **权限与登录更直观**：`gh auth status` 可以快速定位登录状态
- **后续工作流更方便**：可用于创建 Issue/PR、查看 Actions、管理 release 等

### 8.2 安全注意事项

- **禁止提交**：`.env.local`（包含 API Key/Token）
- 建议在 GitHub 仓库启用：
  - 分支保护（Branch protection）
  - Secret scanning（如适用）

## 9. 本次实际产出

- 已在本地初始化 Git 仓库并完成首次提交
- 已安装 GitHub CLI（`gh`）
- 已登录 GitHub（HTTPS）
- 已创建远端仓库并推送：`https://github.com/surdring/SecondBrainOS`
