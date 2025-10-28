import request from '../utils/request'
import type { KnowledgeBase, PaginationResult, PaginationParams } from '@/types'

// 获取知识库列表
export const getKnowledgeBases = (params: PaginationParams & { category_id?: number; status?: string }) => {
  return request<PaginationResult<KnowledgeBase>>({
    url: '/knowledge-bases',
    method: 'get',
    params
  })
}

// 创建知识库
export const createKnowledgeBase = (data: Partial<KnowledgeBase>) => {
  return request<KnowledgeBase>({
    url: '/knowledge-bases',
    method: 'post',
    data
  })
}

// 获取知识库详情
export const getKnowledgeBaseDetail = (id: number) => {
  return request<KnowledgeBase>({
    url: `/knowledge-bases/${id}`,
    method: 'get'
  })
}

// 更新知识库
export const updateKnowledgeBase = (id: number, data: Partial<KnowledgeBase>) => {
  return request<KnowledgeBase>({
    url: `/knowledge-bases/${id}`,
    method: 'put',
    data
  })
}

// 删除知识库
export const deleteKnowledgeBase = (id: number) => {
  return request({
    url: `/knowledge-bases/${id}`,
    method: 'delete'
  })
}

// 获取分类树
export const getCategories = () => {
  return request({
    url: '/knowledge-bases/categories',
    method: 'get'
  })
}

// 创建分类
export const createCategory = (data: any) => {
  return request({
    url: '/knowledge-bases/categories',
    method: 'post',
    data
  })
}

// 更新分类
export const updateCategory = (id: number, data: any) => {
  return request({
    url: `/knowledge-bases/categories/${id}`,
    method: 'put',
    data
  })
}

// 删除分类
export const deleteCategory = (id: number) => {
  return request({
    url: `/knowledge-bases/categories/${id}`,
    method: 'delete'
  })
}

// 获取标签列表
export const getTags = () => {
  return request({
    url: '/knowledge-bases/tags',
    method: 'get'
  })
}

// 创建标签
export const createTag = (data: any) => {
  return request({
    url: '/knowledge-bases/tags',
    method: 'post',
    data
  })
}

// 更新标签
export const updateTag = (id: number, data: any) => {
  return request({
    url: `/knowledge-bases/tags/${id}`,
    method: 'put',
    data
  })
}

// 删除标签
export const deleteTag = (id: number) => {
  return request({
    url: `/knowledge-bases/tags/${id}`,
    method: 'delete'
  })
}

// 获取热门标签
export const getPopularTags = () => {
  return request({
    url: '/knowledge-bases/tags/popular',
    method: 'get'
  })
}

// 推荐分类
export const suggestCategory = (documentId: number) => {
  return request({
    url: `/documents/${documentId}/suggest-category`,
    method: 'post'
  })
}

// 推荐标签
export const suggestTags = (documentId: number) => {
  return request({
    url: `/documents/${documentId}/suggest-tags`,
    method: 'post'
  })
}

// 批量推荐
export const batchSuggest = (documentIds: number[]) => {
  return request({
    url: '/documents/batch-suggest',
    method: 'post',
    data: { document_ids: documentIds }
  })
}

