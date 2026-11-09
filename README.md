# GitHub Pages 简洁主页

这是一个纯静态网站初版，仅包含 `index.html` 和 `styles.css`，无需服务器或构建工具，可直接部署到 GitHub Pages。

## 本地预览

最简单的方式是直接双击 `index.html`，用浏览器打开。

也可以在当前目录启动一个本地服务（需要已安装 Python）：

```powershell
python -m http.server 8000
```

然后访问 <http://localhost:8000>。

## 推送到 GitHub

1. 在 GitHub 新建一个空仓库，不要额外生成 README 或 `.gitignore`。
2. 在本目录打开 PowerShell，依次执行：

```powershell
git add .
git commit -m "Create initial GitHub Pages site"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

以后更新网站时只需：

```powershell
git add .
git commit -m "Update site"
git push
```

## 启用 GitHub Pages

1. 打开 GitHub 仓库的 **Settings**。
2. 在左侧选择 **Pages**。
3. 在 **Build and deployment** 下，将 **Source** 设为 **Deploy from a branch**。
4. 分支选择 `main`，目录选择 `/ (root)`，然后保存。
5. 等待一两分钟，GitHub 会显示网站地址，通常为：

```text
https://你的用户名.github.io/你的仓库名/
```

如果仓库名正好是 `你的用户名.github.io`，地址则是：

```text
https://你的用户名.github.io/
```

## 修改内容

- 页面文字与结构：编辑 `index.html`
- 颜色、字体与布局：编辑 `styles.css`
- 邮箱占位符：搜索 `hello@example.com` 并替换为你的地址
- 圆形头像区域的字母：搜索 `<span>G</span>` 并替换
