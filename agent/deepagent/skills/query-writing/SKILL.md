---
name: query-writing
description: 用于编写和执行 SQL 查询 - 支持多维度分析、多条 SQL 协同、智能图表推荐
---

# 查询编写技能

## 何时使用此技能

当您需要通过编写和执行 SQL 查询来回答问题时应使用此技能。

## 简单查询工作流程

对于涉及单个表的直接问题：

1. **识别表** - 哪个表包含所需数据？
2. **获取架构** - 使用 `sql_db_schema` 查看列
3. **编写查询** - 使用 WHERE/LIMIT/ORDER BY 选择相关列
4. **执行** - 使用 `sql_db_query` 运行
5. **格式化答案** - 清晰地呈现结果

## 复杂查询工作流程

对于需要多个表的问题：

### 1. 规划方法
**使用 `write_todos` 分解任务：**
- 识别所有需要的表
- 映射关系（外键）
- 规划 JOIN 结构
- 确定聚合操作
- 判断是否需要多条 SQL

### 2. 检查架构
对每个表使用 `sql_db_schema` 查找连接列和所需字段。一次传入多表名，减少调用。

### 3. 获取表关系
使用 `sql_db_table_relationship` 获取表间外键关系，确保 JOIN 条件正确。

### 4. 构建查询
- SELECT - 列和聚合函数
- FROM/JOIN - 通过 FK = PK 连接表
- WHERE - 聚合前的过滤条件
- GROUP BY - 所有非聚合列
- ORDER BY - 有意义的排序
- LIMIT - 默认 100 行

### 5. 验证和执行
检查所有 JOIN 都有条件，GROUP BY 正确，然后运行查询。

## SQL 生成规则

1. **只生成 SELECT 查询。** 绝不生成 INSERT/UPDATE/DELETE/DROP/ALTER。
2. **默认附加 LIMIT 100**，除非用户明确指定数量。
3. **使用正确引号**（MySQL 用反引号，PostgreSQL/SQLite 用双引号，SQL Server 用方括号）。
4. **只查询相关列**，不使用 SELECT *。
5. **使用表别名**以提高清晰度（如 `o` for orders, `p` for products）。
6. **日期格式化：** 如果存在时间字段且未指定格式：
   - datetime → `yyyy-MM-dd HH:mm:ss`
   - date → `yyyy-MM-dd`
   - year-month → `yyyy-MM`
7. **多表关联：** 优先使用 schema 中的主键和外键。

## 多维度查询策略

**根据用户问题复杂度，可以生成多条 SQL**，分别获取不同维度的数据：

### 何时使用多条 SQL

| 场景 | 策略 |
|------|------|
| 趋势+归因分析 | SQL1: 时间维度趋势数据；SQL2: 分类维度归因数据 |
| 综合报告 | SQL1: 汇总 KPI；SQL2: 趋势数据；SQL3: 排名/Top N |
| "为什么"类问题 | SQL1: 总体趋势确认变化；SQL2: 按维度分解贡献 |
| 对比分析 | SQL1: 当前周期数据；SQL2: 对比周期数据 |

### 多维度查询意识

根据用户问题，自动判断需要哪些维度的查询：
- **趋势分析** → 包含 ORDER BY time ASC，按时间粒度 GROUP BY
- **分类对比** → 包含 ORDER BY metric DESC，按类别 GROUP BY
- **占比分析** → 包含百分比计算（子查询或窗口函数）
- **归因分析** → 包含多维度 GROUP BY + 增量贡献
- **增长率分析** → 使用窗口函数 LAG() 计算同比/环比

### 每条查询的元信息

为每条 SQL 标注用途和推荐图表类型，便于后续报告生成：

```
查询 1：获取月度趋势数据
推荐图表：折线图/面积图
SQL: SELECT ...

查询 2：获取各品类占比
推荐图表：饼图/环形图
SQL: SELECT ...
```

## 图表类型推荐

| 数据特征 | 推荐图表 | 说明 |
|---------|---------|------|
| 时间序列 | 折线图/面积图 | 展示趋势变化 |
| 分类排名 | 水平柱状图 | Top N 排名展示 |
| 占比结构 | 饼图/环形图 | 各分类占比 |
| 多维对比 | 分组柱状图 | 不同组间指标对比 |
| 变化归因 | 瀑布图 | 各维度对变化的贡献 |
| 趋势+量 | 双轴图 | 柱线组合，展示量和率 |
| 综合评估 | 雷达图 | 多维度能力画像 |
| 增长率分析 | 折线图+数据标签 | 环比/同比变化 |
| 帕累托分析 | 组合图（柱状+累积线） | 头部集中度分析 |
| 异常检测 | 折线图+红色标注 | 偏离均值的异常值 |

## 示例：按国家统计收入

```sql
SELECT
    c.Country,
    ROUND(SUM(i.Total), 2) as TotalRevenue
FROM Invoice i
INNER JOIN Customer c ON i.CustomerId = c.CustomerId
GROUP BY c.Country
ORDER BY TotalRevenue DESC
LIMIT 10;
```

## 示例：多维度销售分析（多条 SQL）

**用户问题：** "分析今年的月度销售趋势，为什么8月特别高？"

**查询 1：月度趋势**
```sql
SELECT
    DATE_FORMAT(order_date, '%Y-%m') as month,
    ROUND(SUM(amount), 2) as total_sales,
    COUNT(*) as order_count
FROM orders
WHERE YEAR(order_date) = 2024
GROUP BY DATE_FORMAT(order_date, '%Y-%m')
ORDER BY month ASC;
```
推荐图表：面积折线图

**查询 2：8月品类分解归因**
```sql
SELECT
    p.category,
    ROUND(SUM(o.amount), 2) as sales,
    COUNT(*) as order_count
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE DATE_FORMAT(o.order_date, '%Y-%m') = '2024-08'
GROUP BY p.category
ORDER BY sales DESC;
```
推荐图表：水平柱状图

**查询 3：8月 vs 7月品类对比**
```sql
SELECT
    p.category,
    ROUND(SUM(CASE WHEN DATE_FORMAT(o.order_date, '%Y-%m') = '2024-08' THEN o.amount ELSE 0 END), 2) as aug_sales,
    ROUND(SUM(CASE WHEN DATE_FORMAT(o.order_date, '%Y-%m') = '2024-07' THEN o.amount ELSE 0 END), 2) as jul_sales,
    ROUND(SUM(CASE WHEN DATE_FORMAT(o.order_date, '%Y-%m') = '2024-08' THEN o.amount ELSE 0 END) -
          SUM(CASE WHEN DATE_FORMAT(o.order_date, '%Y-%m') = '2024-07' THEN o.amount ELSE 0 END), 2) as diff
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE DATE_FORMAT(o.order_date, '%Y-%m') IN ('2024-07', '2024-08')
GROUP BY p.category
ORDER BY diff DESC;
```
推荐图表：瀑布图/堆叠柱状图

## 质量指南

- 只查询相关列（不使用 SELECT *）
- 始终应用 LIMIT（默认 100）
- 使用表别名以提高清晰度
- 对于复杂查询：使用 write_todos 进行规划
- 绝不使用 DML 语句（INSERT, UPDATE, DELETE, DROP）
- SQL 执行失败时：分析错误，修正后重试（最多 2 次）
- 多条 SQL 时，每条标注用途和推荐图表类型
- 聚合查询务必检查 GROUP BY 是否完整
