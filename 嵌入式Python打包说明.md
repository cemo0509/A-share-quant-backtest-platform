# 嵌入式 Python 打包说明

## 目标
将 Python 和所有依赖打包进安装包，用户**无需安装 Python** 即可使用。

## 步骤

### 1. 下载嵌入式 Python
双击运行 `下载嵌入式Python.cmd`，自动下载并解压 Python 3.11.9 到 `python-embed` 目录。

### 2. 安装依赖到嵌入式 Python
双击运行 `安装依赖到嵌入式Python.cmd`，自动将 flask、backtrader 等依赖安装到嵌入式 Python 中。

### 3. 重新打包
运行 `打包桌面版.cmd` 重新打包，此时 `python-embed` 目录会被打包进安装包。

### 4. 测试
安装包安装后，程序会自动使用内置的 Python，无需用户安装。

## 文件说明
- `python-embed/` - 嵌入式 Python 目录（打包进安装包）
- `下载嵌入式Python.cmd` - 下载嵌入式 Python
- `安装依赖到嵌入式Python.cmd` - 安装依赖到嵌入式 Python
- `electron/main.js` - 已修改为优先使用内置 Python

## 注意事项
1. 嵌入式 Python 约 10MB，会使安装包增大
2. 依赖安装后约 100MB，整体安装包约 180MB
3. 用户完全免装 Python，体验更好
