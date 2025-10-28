// 通用类型
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

export interface PaginationParams {
  page: number
  size: number
}

export interface PaginationResult<T> {
  total: number
  items: T[]
  page: number
  size: number
}

// 知识库类型
export interface KnowledgeBase {
  id: number
  name: string
  description: string
  category_id: number
  category_name: string
  status: string
  created_at: string
  updated_at: string
}

// 文档类型
export interface Document {
  id: number
  knowledge_base_id: number
  title: string
  file_name: string
  file_type: string
  file_size: number
  status: string
  created_at: string
  updated_at: string
}

// 用户类型
export interface User {
  id: string
  username: string
  email: string
  role: string
}

