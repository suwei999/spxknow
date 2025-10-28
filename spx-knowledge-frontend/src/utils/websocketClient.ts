import { ElMessage } from 'element-plus'

export interface WebSocketMessage {
  type: string
  [key: string]: any
}

export class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private heartbeatInterval: number | null = null
  private reconnectTimer: number | null = null
  private listeners: Map<string, (data: any) => void> = new Map()
  private onConnectCallback: (() => void) | null = null
  private onDisconnectCallback: (() => void) | null = null
  private onErrorCallback: ((error: Error) => void) | null = null

  constructor(url: string) {
    this.url = url
  }

  /**
   * 连接到WebSocket服务器
   */
  connect(): void {
    try {
      this.ws = new WebSocket(this.url)
      this.setupEventHandlers()
    } catch (error) {
      console.error('WebSocket连接失败:', error)
      this.handleError(new Error('连接失败'))
    }
  }

  /**
   * 设置事件处理器
   */
  private setupEventHandlers(): void {
    if (!this.ws) return

    // 连接打开
    this.ws.onopen = () => {
      console.log('WebSocket已连接')
      this.reconnectAttempts = 0
      this.startHeartbeat()
      if (this.onConnectCallback) {
        this.onConnectCallback()
      }
    }

    // 接收消息
    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.handleMessage(data)
      } catch (error) {
        console.error('消息解析失败:', error)
      }
    }

    // 错误处理
    this.ws.onerror = (error) => {
      console.error('WebSocket错误:', error)
      this.handleError(new Error('WebSocket错误'))
    }

    // 连接关闭
    this.ws.onclose = () => {
      console.log('WebSocket已关闭')
      this.stopHeartbeat()
      
      // 尝试重连
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnect()
      } else {
        if (this.onDisconnectCallback) {
          this.onDisconnectCallback()
        }
      }
    }
  }

  /**
   * 处理接收到的消息
   */
  private handleMessage(data: any): void {
    const type = data.type

    // 处理心跳响应
    if (type === 'pong') {
      return
    }

    // 触发对应的监听器
    if (this.listeners.has(type)) {
      const listener = this.listeners.get(type)
      if (listener) {
        listener(data)
      }
    }

    // 触发通用监听器
    if (this.listeners.has('*')) {
      const listener = this.listeners.get('*')
      if (listener) {
        listener(data)
      }
    }
  }

  /**
   * 发送消息
   */
  send(data: any): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      ElMessage.warning('WebSocket未连接')
      return
    }

    try {
      this.ws.send(JSON.stringify(data))
    } catch (error) {
      console.error('发送消息失败:', error)
      this.handleError(new Error('发送消息失败'))
    }
  }

  /**
   * 订阅消息
   */
  subscribe(type: string, listener: (data: any) => void): void {
    this.listeners.set(type, listener)
  }

  /**
   * 取消订阅
   */
  unsubscribe(type: string): void {
    this.listeners.delete(type)
  }

  /**
   * 设置连接回调
   */
  onConnect(callback: () => void): void {
    this.onConnectCallback = callback
  }

  /**
   * 设置断开回调
   */
  onDisconnect(callback: () => void): void {
    this.onDisconnectCallback = callback
  }

  /**
   * 设置错误回调
   */
  onError(callback: (error: Error) => void): void {
    this.onErrorCallback = callback
  }

  /**
   * 开始心跳
   */
  private startHeartbeat(): void {
    this.stopHeartbeat()
    
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000) as any // 每30秒心跳一次
  }

  /**
   * 停止心跳
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  /**
   * 重连
   */
  private reconnect(): void {
    this.reconnectAttempts++
    console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
    
    // 清除之前的重连定时器
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }

    // 延迟重连（指数退避）
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 30000)
    this.reconnectTimer = setTimeout(() => {
      this.connect()
    }, delay) as any
  }

  /**
   * 处理错误
   */
  private handleError(error: Error): void {
    if (this.onErrorCallback) {
      this.onErrorCallback(error)
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.stopHeartbeat()
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    this.reconnectAttempts = this.maxReconnectAttempts // 停止重连
  }

  /**
   * 获取连接状态
   */
  getReadyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED
  }

  /**
   * 是否已连接
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

