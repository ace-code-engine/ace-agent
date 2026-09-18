# 02 · 文档解析

**目标**：把 Word / Excel / PPT / PDF / 图片里的内容变成模型能用的上下文，同时看清"读"这件事的边界。

**前置**：仓库根目录，Python ≥ 3.10。解析本身**不需要 API Key**（懒加载的解析器是本地代码）；
只有"让模型总结"才需要接真实模型。

## 1. 装你真正需要的解析器

核心零依赖；解析器是**懒加载**的，缺哪个装哪个，不装不会影响其它功能：

```bash
pip install python-docx            # .docx
pip install openpyxl               # .xlsx / .xlsm
pip install python-pptx            # .pptx
pip install pdfplumber pymupdf      # .pdf（pymupdf 还能判断是不是扫描件）
pip install pytesseract pillow      # 图片 OCR（另需系统装 Tesseract）
pip install pdf2image               # 扫描件 PDF → 图片（另需系统装 poppler）
```

旧版格式（`.doc` / `.xls` / `.ppt` / `.wps` / `.et`）会回退到**系统级** LibreOffice 或 antiword——
没装就返回明确的"缺依赖"，而不是给你一段乱码。

## 2. 把文档丢进去

```
examples/02_document_parsing/drop_docs_here/     ← 你放文件的地方（内容不入库）
```

## 3. 让模型读它

```bash
python ai_code.py            # 接真实模型后
```

然后直接在对话里说：

- `读一下 examples/02_document_parsing/drop_docs_here/报告.docx，总结三段要点`
- 或者用 `@file` 快捷方式把文件挂进上下文（`@file` 后按 Tab 有路径补全）

模型会调用 `parse_document`。返回里带 `method`（用了哪条解析路径：文本提取 / OCR / 表格）
和 `truncated` 标记——大文件会被截断而不是把上下文撑爆。

## 4. 顺带看边界（这才是重点）

| 试着说 | 应该看到 | 为什么 |
|---|---|---|
| `读一下 ~/文档/合同.pdf` | `403` 路径越界 | `parse_document` 与 `file_read`**同一口径**：只允许项目目录内。此前它自己算路径、连越界都不判，能把项目外任意文件读进上下文（BACKLOG `SEC-02`，v3.2 已修） |
| `读一下 ~/.ssh/id_rsa` | `403` 敏感目标 | 密钥类文件即便在项目内也拦 |
| 用一个指向项目外的软链接 | `403` | 命中判定在**解析软链接之后**再确认落点 |
| `grep` 一个 `../` 开头的 pattern | `403`（不是"无匹配"） | 静静丢掉会让模型以为"没找到"，换个写法接着试 |

读的边界说明见 [`docs/SECURITY-MODEL.md`](../../docs/SECURITY-MODEL.md)，
检索工具的细节见 [`docs/CONFIGURATION.md`](../../docs/CONFIGURATION.md) 的「检索工具的边界」。
