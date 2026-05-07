# 民航知识图谱查看器

基于 CCAR-121/145/21/26 条款卡片构建的知识图谱交互查看器。

## 访问地址

部署后访问：`https://[你的GitHub用户名].github.io/[仓库名]/`

例如：`https://username.github.io/kb-graph/`

## 本地预览

```bash
cd kb-graph
python3 -m http.server 8080
# 浏览器打开 http://localhost:8080
```

## 功能

- 条款搜索（条款号、章节、标签）
- 点击节点查看详情（摘要、标签、引用关系）
- 图谱可视化（可缩放、拖拽）
- 颜色区分规章（蓝=CCAR-121，绿=CCAR-145，红=CCAR-21，紫=CCAR-26）

## GitHub Pages 部署步骤

1. 创建新仓库，名字任意（如 `kb-graph`）
2. 将本仓库所有文件上传到仓库根目录
3. Settings → Pages → Source: `main` branch, `/ (root)` → Save
4. 等待 2-3 分钟，访问 `[username].github.io/[仓库名]/`

## 数据来源

- CCAR-121 大型飞机公共航空运输承运人运行合格审定规则（R8）
- CCAR-145 民用航空器维修单位合格审定规定（R4）
- CCAR-21 民用航空产品和零部件合格审定规定（R5）
- CCAR-26 运输类飞机的持续适航和安全改进规定（R0）

---

Built 2026-05-07 | OpenClaw
