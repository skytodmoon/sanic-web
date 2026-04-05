---
name: schema-exploration
description: 用于发现和理解数据库结构、表、列和关系，支持 M-Schema 格式输出，智能表过滤
---

# 架构探索技能

## 何时使用此技能

当您需要以下操作时使用此技能：
- 理解数据库结构
- 查找包含特定类型数据的表
- 发现列名和数据类型
- 映射表之间的关系
- 为 SQL 生成准备 M-Schema 格式的结构信息
- 回答诸如"有哪些表可用？"或"Customer 表有哪些列？"等问题

## 工作流程

### 1. 列出所有表

使用 `sql_db_list_tables` 工具查看数据库中所有可用的表。

这将返回您可以查询的完整表列表。

### 2. 智能表过滤（针对复杂查询）

当数据库表较多时，不要盲目获取所有表的 schema，而是先进行智能过滤：

1. **获取表列表后**，根据用户问题进行语义分析，提取关键实体和意图
2. **匹配策略**：
   - 将关键词与表名、表注释进行语义匹配（如"销售额" → 可能涉及 orders、sales、products 等表）
   - 考虑表之间的潜在关联（如用户问"客户订单"，需要同时选中 customers 和 orders）
   - 忽略明显无关的系统表、日志表、临时表
3. **输出**：筛选后的相关表名列表（通常 3-8 张表）

**内部思考模板：**
```
用户问题：{user_question}

数据库所有表：
- {table1}, {table2}, ...

任务：从上述表中选出与用户问题直接相关的表。
考虑因素：
1. 表名是否与问题中的实体/指标匹配
2. 是否需要关联表来补充维度信息
3. 忽略明显无关的系统表、日志表

选出的相关表：[table1, table2, ...]
```

### 3. 获取特定表的架构

使用 `sql_db_schema` 工具配合表名来检查：
- **列名** - 有哪些字段可用
- **数据类型** - INTEGER, TEXT, DATETIME 等
- **示例数据** - 示例数据以了解内容
- **主键** - 行的唯一标识符
- **外键** - 与其他表的关系
- **列注释** - 字段含义说明

**提示**：可以一次传入多个表名（逗号分隔），减少工具调用次数。

### 4. 获取表关系

使用 `sql_db_table_relationship` 工具获取表之间的外键/关联关系：
- **关联字段** - 两表通过哪些字段关联
- **JOIN 条件** - 返回格式如 `t_orders.customer_id = t_customers.id`

示例调用：
```
sql_db_table_relationship("t_orders, t_customers, t_products")
```

如果未配置表关系，可以通过以下方式推断：
- 查找以 "Id" 或 "_id" 结尾的列（例如，customer_id, product_id）
- 外键列名通常对应另一个表的主键
- 记录父子关系

### 5. 生成 M-Schema 格式（用于 SQL 生成）

当需要将 schema 信息传递给后续 SQL 生成步骤时，使用 M-Schema 格式组织信息：

```
【DB_ID】 {db_name}
【Schema】
# Table: {table_name}, {table_comment}
[
  ({column_name}:{column_type}, {column_comment}),
]
{foreign_key_1}
{foreign_key_2}
```

**数据库特定规则：**
- PostgreSQL/Oracle/SQL Server: 使用 `schema.table_name` 格式
- MySQL/ClickHouse/SQLite: 使用纯 `table_name`

**引号规则：**
| 数据库类型 | 引号 |
|-----------|------|
| MySQL | \`反引号\` |
| PostgreSQL | "双引号" |
| SQLite | "双引号" |
| SQL Server | [方括号] |
| Oracle | "双引号" |
| ClickHouse | "双引号" |

### 6. 回答问题

提供清晰的信息：
- 可用表及其用途
- 列名及其包含的内容
- 表之间的关联方式
- 示例数据以说明内容

## 示例："有哪些表可用？"

**步骤 1：** 使用 `sql_db_list_tables`

**响应：**
```
数据库包含多个表：
1. Customer - 存储客户信息
2. Employee - 存储员工信息
3. Invoice - 客户购买记录
4. InvoiceLine - 发票中的单个项目
...
```

## 示例："这些表之间有什么关系？"

**步骤 1：** 使用 `sql_db_table_relationship("Customer, Invoice, InvoiceLine")`

**响应：**
```
表之间的关系如下：
  • Invoice.CustomerId = Customer.Id
  • InvoiceLine.InvoiceId = Invoice.Id

✅ 表关系已获取完成。
```

## 示例："准备查询销售额数据的 M-Schema"

**步骤 1：** `sql_db_list_tables` → 智能过滤出 orders, products, customers
**步骤 2：** `sql_db_schema("orders, products, customers")` → 获取完整 schema
**步骤 3：** `sql_db_table_relationship("orders, products, customers")` → 获取关系
**步骤 4：** 组织为 M-Schema 格式：

```
【DB_ID】 sales_db
【Schema】
# Table: orders, 订单表
[
  (id:INTEGER, 订单ID),
  (customer_id:INTEGER, 客户ID),
  (product_id:INTEGER, 产品ID),
  (amount:DECIMAL, 订单金额),
  (order_date:DATETIME, 下单时间),
]
orders.customer_id = customers.id
orders.product_id = products.id

# Table: products, 产品表
[
  (id:INTEGER, 产品ID),
  (name:VARCHAR, 产品名称),
  (category:VARCHAR, 产品类别),
  (price:DECIMAL, 单价),
]

# Table: customers, 客户表
[
  (id:INTEGER, 客户ID),
  (name:VARCHAR, 客户名称),
  (region:VARCHAR, 所属区域),
]
```

## 质量指南

**对于"列出表"问题：**
- 显示所有表名
- 添加每个表包含内容的简要描述
- 对相关表进行分组（例如，交易、人员）

**对于"描述表"问题：**
- 列出所有列及其数据类型
- 解释每列包含的内容
- 显示示例数据以提供上下文
- 注明主键和外键
- 解释与其他表的关系

**对于"如何查询 X"问题：**
- 识别所需的表
- 映射 JOIN 路径
- 解释关系链
- 建议下一步（使用查询编写技能）

**对于复杂查询准备：**
- 使用智能表过滤，只选相关表
- 生成 M-Schema 格式供 SQL 生成使用
- 明确标注表关系和 JOIN 条件

## 常见探索模式

### 模式 1：查找表
"哪个表包含客户信息？"
→ 使用 list_tables，然后描述 Customer 表

### 模式 2：理解结构
"Invoice 表中有什么？"
→ 使用 schema 工具显示列和示例数据

### 模式 3：映射关系
"客户如何与发票关联？"
→ 使用 `sql_db_table_relationship("Customer, Invoice, InvoiceLine")` 获取关系

### 模式 4：查询准备
"我要分析各产品销售情况"
→ 智能过滤 → 获取 schema → 获取关系 → 输出 M-Schema

## 提示

- 外键通常以 "Id" 结尾，并匹配表名
- 使用示例数据了解值的格式
- 不确定使用哪个表时，先列出所有表
- 获取 schema 时尽量一次传入多个相关表名，减少工具调用
- M-Schema 格式有助于后续 SQL 生成的准确性
