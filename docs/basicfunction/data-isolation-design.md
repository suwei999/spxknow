# 数据隔离与权限管理设计文档

## 1. 当前实现（v1.0 - 基础隔离）

### 1.1 设计原则
- **完全隔离**：每个用户只能访问和管理自己创建的数据
- **自动过滤**：所有查询自动添加 `user_id` 过滤条件
- **创建关联**：创建数据时自动关联当前用户ID

### 1.2 实现方式

#### 后端实现
```python
# 1. 查询时自动过滤
def get_knowledge_bases_paginated(self, page: int, size: int, user_id: int):
    base_query = self.db.query(KnowledgeBase).filter(
        KnowledgeBase.is_deleted == False,
        KnowledgeBase.user_id == user_id  # 自动过滤
    )
    # ...

# 2. 创建时自动关联
def create_knowledge_base(self, kb_data, user_id: int):
    kb_data["user_id"] = user_id  # 自动关联
    # ...

# 3. 更新/删除时验证归属权
def update_knowledge_base(self, kb_id: int, user_id: int):
    kb = self.db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.user_id == user_id  # 验证归属
    ).first()
    if not kb:
        raise HTTPException(403, "无权访问")
    # ...
```

#### 数据模型
- `knowledge_bases.user_id` - 知识库所有者
- `documents.user_id` - 文档所有者
- `qa_sessions.user_id` - 问答会话所有者
- `operation_logs.user_id` - 操作日志关联

### 1.3 优点
✅ **简单清晰**：实现简单，逻辑明确
✅ **安全性高**：数据完全隔离，用户无法访问他人数据
✅ **性能好**：查询时直接过滤，无需额外权限检查
✅ **易于理解**：开发者容易理解和维护

### 1.4 局限性
❌ **无法共享**：用户无法共享知识库给他人
❌ **无法协作**：不支持团队协作场景
❌ **无法公开**：不支持公开知识库
❌ **扩展性差**：未来如需团队功能，需要重构

---

## 2. 改进方案对比

### 方案A：共享知识库（推荐 - 渐进式升级）

#### 设计思路
在现有基础上，增加共享功能，支持：
- 知识库所有者可以邀请其他用户
- 被邀请用户可以有不同权限（只读、编辑、管理员）
- 保持向后兼容，现有数据不受影响

#### 数据模型扩展
```sql
-- 知识库成员表
CREATE TABLE `knowledge_base_members` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `knowledge_base_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    `role` VARCHAR(20) DEFAULT 'viewer' COMMENT '角色: owner/viewer/editor/admin',
    `invited_by` INT COMMENT '邀请人ID',
    `invited_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_kb_member` (`knowledge_base_id`, `user_id`),
    FOREIGN KEY (`knowledge_base_id`) REFERENCES `knowledge_bases` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) COMMENT='知识库成员表';

-- 知识库表增加共享设置
ALTER TABLE `knowledge_bases` 
ADD COLUMN `is_public` BOOLEAN DEFAULT FALSE COMMENT '是否公开',
ADD COLUMN `share_code` VARCHAR(32) COMMENT '分享码（用于公开访问）';
```

#### 权限模型
```
角色定义：
- owner（所有者）：完全控制，可删除、邀请成员、修改设置
- admin（管理员）：可编辑、邀请成员、修改设置（不能删除）
- editor（编辑者）：可编辑内容、上传文档
- viewer（查看者）：只能查看，不能编辑
```

#### 查询逻辑调整
```python
def get_knowledge_bases_paginated(self, page: int, size: int, user_id: int):
    # 查询：用户拥有的 + 用户被邀请的
    base_query = self.db.query(KnowledgeBase).join(
        KnowledgeBaseMember,
        KnowledgeBase.id == KnowledgeBaseMember.knowledge_base_id
    ).filter(
        KnowledgeBase.is_deleted == False,
        or_(
            KnowledgeBase.user_id == user_id,  # 自己创建的
            KnowledgeBaseMember.user_id == user_id  # 被邀请的
        )
    )
    # ...
```

#### 优点
✅ **向后兼容**：现有数据不受影响
✅ **渐进式升级**：可以逐步迁移
✅ **灵活性高**：支持多种协作场景
✅ **易于实现**：在现有基础上扩展

#### 缺点
⚠️ **复杂度增加**：需要管理成员关系
⚠️ **性能影响**：查询需要 JOIN 操作

---

### 方案B：组织/团队模式（企业级）

#### 设计思路
引入组织（Organization）和团队（Team）概念：
- 用户可以创建或加入组织
- 组织内可以创建团队
- 知识库属于组织或团队
- 支持多层级权限管理

#### 数据模型
```sql
-- 组织表
CREATE TABLE `organizations` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `owner_id` INT NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 组织成员表
CREATE TABLE `organization_members` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `organization_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    `role` VARCHAR(20) DEFAULT 'member',
    UNIQUE KEY `uk_org_member` (`organization_id`, `user_id`)
);

-- 知识库关联组织
ALTER TABLE `knowledge_bases`
ADD COLUMN `organization_id` INT COMMENT '所属组织',
ADD COLUMN `team_id` INT COMMENT '所属团队';
```

#### 优点
✅ **企业级功能**：适合大型团队
✅ **权限精细**：支持复杂的权限管理
✅ **数据集中**：组织数据统一管理

#### 缺点
❌ **复杂度高**：实现和维护成本高
❌ **过度设计**：对于个人用户来说太复杂
❌ **迁移成本**：需要大量重构

---

### 方案C：混合模式（推荐 - 长期方案）

#### 设计思路
结合方案A和方案B的优点：
- **个人模式**：保持现有的个人数据隔离
- **共享模式**：支持知识库共享和协作
- **组织模式**：可选的组织/团队功能（未来扩展）

#### 实现策略
1. **第一阶段**（当前）：保持完全隔离
2. **第二阶段**：添加共享功能（方案A）
3. **第三阶段**：可选的组织功能（方案B）

#### 数据模型设计
```sql
-- 知识库表：支持多种模式
ALTER TABLE `knowledge_bases`
ADD COLUMN `visibility` VARCHAR(20) DEFAULT 'private' COMMENT '可见性: private/shared/public',
ADD COLUMN `organization_id` INT NULL COMMENT '所属组织（可选）';

-- 共享成员表（用于共享模式）
CREATE TABLE `knowledge_base_members` (
    -- 同方案A
);

-- 组织表（用于组织模式，可选）
CREATE TABLE `organizations` (
    -- 同方案B
);
```

---

## 3. 推荐方案：渐进式升级路径

### 阶段1：当前实现（已完成）
- ✅ 完全数据隔离
- ✅ 用户只能访问自己的数据
- ✅ 简单、安全、高效

### 阶段2：添加共享功能（建议下一步）
**时间估算**：2-3周
**优先级**：高

**功能清单**：
1. 知识库成员管理
   - 邀请用户（通过用户名/邮箱）
   - 设置权限（viewer/editor/admin）
   - 移除成员
2. 共享知识库查询
   - 列表显示：自己创建的 + 被邀请的
   - 权限标识：显示角色（所有者/管理员/编辑者/查看者）
3. 权限控制
   - 查看权限：所有成员可查看
   - 编辑权限：editor/admin/owner 可编辑
   - 管理权限：admin/owner 可管理成员
   - 删除权限：仅 owner 可删除

**API 设计**：
```python
# 邀请成员
POST /api/knowledge-bases/{kb_id}/members
{
    "user_id": 2,
    "role": "editor"
}

# 获取成员列表
GET /api/knowledge-bases/{kb_id}/members

# 更新成员权限
PUT /api/knowledge-bases/{kb_id}/members/{user_id}
{
    "role": "admin"
}

# 移除成员
DELETE /api/knowledge-bases/{kb_id}/members/{user_id}
```

### 阶段3：公开知识库（可选）
**时间估算**：1周
**优先级**：中

**功能清单**：
1. 知识库可设置为公开
2. 生成分享链接（带分享码）
3. 公开知识库无需登录即可查看（只读）

### 阶段4：组织/团队功能（未来）
**时间估算**：4-6周
**优先级**：低

**功能清单**：
1. 创建/加入组织
2. 组织内创建团队
3. 知识库关联组织/团队
4. 组织级权限管理

---

## 4. 实施建议

### 4.1 当前阶段（保持现状）
**建议**：保持当前的完全隔离设计，因为：
- ✅ 满足个人用户需求
- ✅ 实现简单，维护成本低
- ✅ 安全性高

### 4.2 下一步优化（共享功能）
**建议**：如果用户有协作需求，实施阶段2的共享功能

**实施步骤**：
1. 设计并评审数据模型扩展
2. 创建迁移脚本
3. 实现成员管理API
4. 调整查询逻辑（支持共享查询）
5. 前端UI：成员管理界面
6. 测试和文档

### 4.3 长期规划
根据实际业务需求，逐步添加：
- 公开知识库
- 组织/团队功能
- 更细粒度的权限控制

---

## 5. 总结

### 当前设计评价
- **适用场景**：个人知识管理、小型团队
- **优点**：简单、安全、高效
- **缺点**：不支持协作、共享

### 改进建议
1. **短期**：保持现状，满足个人用户需求
2. **中期**：添加共享功能，支持团队协作
3. **长期**：根据业务需求，考虑组织/团队功能

### 决策建议
- **如果主要是个人使用**：保持当前设计
- **如果需要团队协作**：实施阶段2（共享功能）
- **如果是企业级应用**：考虑阶段4（组织功能）

---

**文档版本**：v1.0  
**创建日期**：2025-01-23  
**最后更新**：2025-01-23

