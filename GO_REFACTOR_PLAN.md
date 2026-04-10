# CPL 广告管理平台 - Go 语言重构计划

**参考架构：** E:\GoPlatform (SDK 广告后台管理系统)  
**目标项目：** E:\Platform (CPL 广告管理后台)  
**分析日期：** 2026-04-10  
**作者：** 钳钱 🦀💰

---

## 📊 项目对比分析

### 当前状态 (Python)

| 指标 | Platform (Python) | GoPlatform (Go) |
|------|------------------|-----------------|
| 代码文件数 | 269 个 .py 文件 | 70 个 .go 文件 |
| 代码行数 | ~35,000 行 | ~8,000 行 |
| 启动时间 | ~5 秒 | <1 秒 |
| 内存占用 | ~300MB | ~50MB |
| 并发能力 | 中等 (asyncio) | 高 (goroutine) |
| 部署复杂度 | 高 (venv + 依赖) | 低 (单二进制) |

### 重构收益预估

| 指标 | 预期改善 |
|------|----------|
| 性能 | 提升 3-5 倍 |
| 内存 | 降低 60-80% |
| 启动速度 | 提升 5 倍 |
| 部署简化 | 单二进制文件 |
| 类型安全 | 编译时检查 |

---

## 🏗️ GoPlatform 架构分析

### 目录结构

```
E:\GoPlatform/
├── cmd/                          # 应用程序入口
│   ├── server/                   # 主服务
│   │   └── main.go
│   ├── ad-report-service/        # 广告报告服务
│   │   └── main.go
│   └── scheduler/                # 定时任务服务
│       └── main.go
├── api/                          # API 层 (HTTP  handlers)
│   ├── routes.go                 # 路由定义
│   ├── handlers/
│   │   ├── user_handler.go       # 用户处理器
│   │   ├── offer_handler.go      # Offer 处理器
│   │   ├── click_handler.go      # Click 处理器
│   │   └── conversion_handler.go # 转化处理器
│   ├── middleware/
│   │   ├── auth.go               # JWT 认证中间件
│   │   ├── cors.go               # CORS 中间件
│   │   ├── ratelimit.go          # 限流中间件
│   │   └── logger.go             # 日志中间件
│   └── request/                  # 请求结构体
│       ├── user_request.go
│       └── offer_request.go
├── internal/                     # 内部业务逻辑 (私有包)
│   ├── security/
│   │   ├── jwt.go                # JWT 认证
│   │   ├── password.go           # 密码加密
│   │   └── permission.go         # 权限控制
│   ├── admin/
│   │   ├── user.go               # 用户管理
│   │   ├── role.go               # 角色管理
│   │   └── audit.go               # 审计日志
│   ├── ad/
│   │   ├── offer.go              # Offer 管理
│   │   ├── publisher.go          # 发布商管理
│   │   ├── advertiser.go         # 广告主管理
│   │   ├── click.go              # Click 追踪
│   │   └── conversion.go         # 转化管理
│   ├── report/
│   │   ├── daily_report.go       # 日报生成
│   │   └── real_time.go          # 实时数据
│   ├── cache/
│   │   ├── redis.go              # Redis 客户端
│   │   └── manager.go            # 缓存管理器
│   └── scheduler/
│       ├── cron.go               # 定时任务
│       └── tasks.go              # 任务定义
├── pkg/                          # 公共包 (可复用)
│   ├── database/
│   │   ├── mysql.go              # MySQL 连接
│   │   └── postgres.go           # PostgreSQL 连接
│   ├── logger/
│   │   └── zap.go                # Zap 日志
│   ├── config/
│   │   └── viper.go              # Viper 配置
│   └── utils/
│       ├── hash.go               # 哈希工具
│       └── time.go               # 时间工具
├── configs/                      # 配置文件
│   ├── config.yaml               # 主配置
│   └── config.local.yaml         # 本地配置
├── scripts/                      # 运维脚本
├── deploy/                       # 部署配置
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   └── systemd/
├── go.mod                        # Go 模块定义
├── go.sum                        # 依赖校验
└── README.md                     # 项目文档
```

### 核心设计模式

#### 1. 分层架构

```
HTTP Request
    ↓
api/handlers (路由 + 参数验证)
    ↓
internal/* (业务逻辑)
    ↓
pkg/database (数据访问)
    ↓
MySQL / Redis
```

#### 2. 依赖注入

```go
// internal/ad/offer.go
type OfferService struct {
    db     *database.MySQL
    cache  *cache.Manager
    logger *zap.Logger
}

func NewOfferService(db *database.MySQL, cache *cache.Manager, logger *zap.Logger) *OfferService {
    return &OfferService{db: db, cache: cache, logger: logger}
}
```

#### 3. 统一响应格式

```go
// api/response.go
type Response struct {
    Code    int         `json:"code"`
    Message string      `json:"message"`
    Data    interface{} `json:"data"`
}

func Success(data interface{}) Response {
    return Response{Code: 200, Message: "success", Data: data}
}

func Error(code int, message string) Response {
    return Response{Code: code, Message: message}
}
```

---

## 🎯 Platform 项目 Go 重构方案

### 目标架构 (参考 GoPlatform)

```
E:\Platform/
├── cmd/
│   ├── server/                   # 主服务 (FastAPI 替代)
│   │   └── main.go
│   ├── postback-service/         # Postback 处理服务
│   │   └── main.go
│   └── scheduler/                # 定时任务服务
│       └── main.go
├── api/
│   ├── routes.go                 # 路由定义
│   ├── handlers/
│   │   ├── auth_handler.go       # 认证处理器
│   │   ├── ad_data_handler.go    # 广告数据处理器
│   │   ├── client_handler.go     # 客户处理器
│   │   ├── product_handler.go    # 产品处理器
│   │   ├── postback_handler.go   # Postback 处理器
│   │   └── dashboard_handler.go  # 仪表盘处理器
│   ├── middleware/
│   │   ├── auth.go               # JWT 认证
│   │   ├── cors.go               # CORS
│   │   ├── ratelimit.go          # 限流
│   │   ├── audit.go              # 审计日志
│   │   └── recover.go            # Panic 恢复
│   └── request/
│       ├── ad_data_request.go
│       ├── client_request.go
│       └── postback_request.go
├── internal/
│   ├── security/
│   │   ├── jwt.go                # JWT (RS256)
│   │   ├── password.go           # bcrypt
│   │   ├── permission.go         # 角色权限
│   │   └── ip_whitelist.go       # IP 白名单
│   ├── auth/
│   │   ├── user.go               # 用户管理
│   │   └── token.go              # Token 管理
│   ├── client/
│   │   ├── service.go            # 客户服务
│   │   └── repository.go         # 客户数据访问
│   ├── product/
│   │   ├── service.go            # 产品服务
│   │   └── repository.go         # 产品数据访问
│   ├── addata/
│   │   ├── service.go            # 广告数据服务
│   │   ├── repository.go         # 数据访问
│   │   ├── calculator.go         # 指标计算 (CTR/CVR/eCPM)
│   │   └── exporter.go           # Excel 导出
│   ├── postback/
│   │   ├── processor.go          # 转化处理器
│   │   ├── validator.go          # 数据验证
│   │   ├── click_associator.go   # Click 关联
│   │   ├── cap_checker.go        # Cap 检查
│   │   ├── discount.go           # 扣量计算
│   │   ├── forwarder.go          # 转发器
│   │   └── notifier.go           # 通知发送
│   ├── facebook/
│   │   ├── pixel.go              # Facebook 像素上报
│   │   ├── converter.go          # 事件转换
│   │   └── hasher.go             # 数据哈希
│   ├── telegram/
│   │   ├── bot.go                # Telegram Bot
│   │   ├── notifier.go           # 通知发送
│   │   └── command.go            # 命令处理
│   ├── cache/
│   │   ├── redis.go              # Redis 客户端
│   │   ├── manager.go            # 缓存管理器
│   │   └── keys.go               # 缓存键定义
│   ├── scheduler/
│   │   ├── cron.go               # 定时任务
│   │   ├── tasks.go              # 任务定义
│   │   └── sync.go               # 数据同步
│   └── audit/
│       ├── logger.go             # 审计日志
│       └── repository.go         # 日志存储
├── pkg/
│   ├── database/
│   │   ├── mysql.go              # MySQL 连接池
│   │   ├── transaction.go        # 事务管理
│   │   └── migration.go          # 数据库迁移
│   ├── logger/
│   │   └── zap.go                # Zap 日志
│   ├── config/
│   │   └── viper.go              # Viper 配置
│   ├── utils/
│   │   ├── hash.go               # SHA256 哈希
│   │   ├── time.go               # 时间工具 (Asia/Shanghai)
│   │   ├── ip.go                 # IP 工具
│   │   └── excel.go              # Excel 导出
│   └── response/
│       └── response.go           # 统一响应
├── internal/models/              # GORM 模型
│   ├── user.go
│   ├── client.go
│   ├── product.go
│   ├── ad_data.go
│   ├── postback_conversion.go
│   └── ...
├── configs/
│   ├── config.yaml               # 主配置
│   ├── config.local.yaml         # 本地配置
│   └── keys/                     # RSA 密钥
├── scripts/
│   ├── build.sh                  # 构建脚本
│   ├── deploy.sh                 # 部署脚本
│   └── migrate.go                # 数据库迁移
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   └── systemd/
│       └── platform.service
├── go.mod
├── go.sum
└── README.md
```

---

## 📦 依赖映射 (Python → Go)

| Python 包 | Go 替代方案 | 说明 |
|-----------|------------|------|
| **Web 框架** | | |
| fastapi | gin-gonic/gin | 高性能 HTTP 框架 |
| uvicorn | 内置 | Gin 自带 HTTP 服务器 |
| **数据库** | | |
| sqlalchemy | gorm.io/gorm | ORM 框架 |
| aiomysql | gorm.io/driver/mysql | MySQL 驱动 |
| **缓存** | | |
| redis | go-redis/redis | Redis 客户端 |
| **安全** | | |
| python-jose | golang-jwt/jwt | JWT 实现 |
| passlib | golang.org/x/crypto/bcrypt | 密码加密 |
| cryptography | crypto/rsa | RSA 加密 |
| **配置** | | |
| pydantic | github.com/go-playground/validator | 数据验证 |
| - | github.com/spf13/viper | 配置管理 |
| **日志** | | |
| logging | go.uber.org/zap | 高性能日志 |
| **定时任务** | | |
| apscheduler | github.com/robfig/cron | Cron 调度 |
| **HTTP 客户端** | | |
| httpx | net/http | 标准库 |
| **Excel** | | |
| openpyxl | github.com/xuri/excelize/v2 | Excel 处理 |
| **Telegram Bot** | | |
| pyTelegramBotAPI | gopkg.in/telebot.v3 | Telegram Bot |

---

## 🗄️ 数据库模型映射

### Python SQLAlchemy → Go GORM

#### 用户模型

**Python (当前):**
```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="CLIENT")  # ADMIN | CLIENT
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
```

**Go (重构后):**
```go
// internal/models/user.go
package models

import (
    "time"
    "gorm.io/gorm"
)

type User struct {
    ID             uint           `gorm:"primaryKey" json:"id"`
    Username       string         `gorm:"size:50;uniqueIndex;not null" json:"username"`
    HashedPassword string         `gorm:"size:255;not null" json:"-"`
    Role           string         `gorm:"size:20;default:'CLIENT'" json:"role"` // ADMIN | CLIENT
    CreatedAt      time.Time      `json:"created_at"`
    UpdatedAt      time.Time      `json:"-"`
    DeletedAt      gorm.DeletedAt `gorm:"index" json:"-"`
    IsActive       bool           `gorm:"default:true" json:"is_active"`
    
    // 关联
    Client *Client `gorm:"foreignKey:UserID" json:"client,omitempty"`
}

func (User) TableName() string {
    return "users"
}
```

#### 广告数据模型

**Python (当前):**
```python
class AdData(Base):
    __tablename__ = "ad_data"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    impressions = Column(BigInteger, default=0)
    clicks = Column(BigInteger, default=0)
    conversions = Column(BigInteger, default=0)
    revenue = Column(Numeric(10, 4), default=0)
    ecpm = Column(Numeric(10, 4), default=0)
    ctr = Column(Numeric(5, 4), default=0)
    cvr = Column(Numeric(5, 4), default=0)
    
    product = relationship("Product", back_populates="ad_data")
```

**Go (重构后):**
```go
// internal/models/ad_data.go
package models

import (
    "time"
    "database/sql/driver"
    "gorm.io/gorm"
)

type AdData struct {
    ID          uint           `gorm:"primaryKey" json:"id"`
    ProductID   uint           `gorm:"not null;index" json:"product_id"`
    Date        time.Time      `gorm:"type:date;not null;index" json:"date"`
    Impressions int64          `gorm:"default:0" json:"impressions"`
    Clicks      int64          `gorm:"default:0" json:"clicks"`
    Conversions int64          `gorm:"default:0" json:"conversions"`
    Revenue     float64        `gorm:"type:decimal(10,4);default:0" json:"revenue"`
    Ecpm        float64        `gorm:"type:decimal(10,4);default:0" json:"ecpm"`
    Ctr         float64        `gorm:"type:decimal(5,4);default:0" json:"ctr"`
    Cvr         float64        `gorm:"type:decimal(5,4);default:0" json:"cvr"`
    
    // 自动时间戳
    CreatedAt   time.Time      `json:"-"`
    UpdatedAt   time.Time      `json:"-"`
    
    // 关联
    Product     Product        `gorm:"foreignKey:ProductID" json:"product,omitempty"`
}

func (AdData) TableName() string {
    return "ad_data"
}

// BeforeSave 自动计算 CTR 和 CVR
func (a *AdData) BeforeSave(tx *gorm.DB) error {
    if a.Impressions > 0 {
        a.Ctr = float64(a.Clicks) / float64(a.Impressions)
    }
    if a.Clicks > 0 {
        a.Cvr = float64(a.Conversions) / float64(a.Clicks)
    }
    if a.Impressions > 0 {
        a.Ecpm = a.Revenue / float64(a.Impressions) * 1000
    }
    return nil
}
```

#### Postback 转化模型

**Python (当前):**
```python
class PostbackConversion(Base):
    __tablename__ = "postback_conversion"
    
    id = Column(Integer, primary_key=True, index=True)
    click_id = Column(String(100), unique=True, index=True)
    event_id = Column(String(255), unique=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    payout = Column(Numeric(10, 4), default=0)
    status = Column(String(20), default="pending")  # pending | approved | rejected
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
```

**Go (重构后):**
```go
// internal/models/postback_conversion.go
package models

import (
    "time"
    "gorm.io/gorm"
)

type ConversionStatus string

const (
    StatusPending   ConversionStatus = "pending"
    StatusApproved  ConversionStatus = "approved"
    StatusRejected  ConversionStatus = "rejected"
)

type PostbackConversion struct {
    ID        uint             `gorm:"primaryKey" json:"id"`
    ClickID   string           `gorm:"size:100;uniqueIndex;not null" json:"click_id"`
    EventID   string           `gorm:"size:255;uniqueIndex" json:"event_id"`
    ProductID uint             `gorm:"index" json:"product_id"`
    Payout    float64          `gorm:"type:decimal(10,4);default:0" json:"payout"`
    Status    ConversionStatus `gorm:"size:20;default:'pending'" json:"status"`
    IPAddress string           `gorm:"size:45" json:"ip_address"`
    UserAgent string           `gorm:"type:text" json:"user_agent"`
    
    // 扣量字段
    OriginalPayout  float64 `gorm:"type:decimal(10,4)" json:"original_payout"`
    DeductedPayout  float64 `gorm:"type:decimal(10,4)" json:"deducted_payout"`
    DeductionRate   float64 `gorm:"type:decimal(5,4)" json:"deduction_rate"`
    
    // 时间戳
    CreatedAt time.Time      `json:"created_at"`
    UpdatedAt time.Time      `json:"-"`
    DeletedAt gorm.DeletedAt `gorm:"index" json:"-"`
    
    // 关联
    Product Product `gorm:"foreignKey:ProductID" json:"product,omitempty"`
}

func (PostbackConversion) TableName() string {
    return "postback_conversion"
}
```

---

## 🔌 API 路由映射

### 当前 Python API → Go API

| Python 路由 | Go 路由 | 说明 |
|------------|--------|------|
| `POST /api/v1/auth/login` | `POST /api/v1/auth/login` | 登录 |
| `POST /api/v1/auth/logout` | `POST /api/v1/auth/logout` | 登出 |
| `GET /api/v1/auth/me` | `GET /api/v1/auth/me` | 当前用户 |
| `GET /api/v1/ad-data` | `GET /api/v1/ad-data` | 广告数据列表 |
| `GET /api/v1/ad-data/{id}` | `GET /api/v1/ad-data/:id` | 广告数据详情 |
| `POST /api/v1/ad-data` | `POST /api/v1/ad-data` | 创建广告数据 |
| `PUT /api/v1/ad-data/{id}` | `PUT /api/v1/ad-data/:id` | 更新广告数据 |
| `DELETE /api/v1/ad-data/{id}` | `DELETE /api/v1/ad-data/:id` | 删除广告数据 |
| `GET /api/v1/ad-data/stats` | `GET /api/v1/ad-data/stats` | 统计数据 |
| `GET /api/v1/dashboard/summary` | `GET /api/v1/dashboard/summary` | 仪表盘汇总 |
| `POST /api/v1/postback` | `POST /api/v1/postback` | 接收转化 |
| `POST /api/v1/third-party-report/facebook` | `POST /api/v1/facebook/report` | Facebook 上报 |

### Go Handler 示例

```go
// api/handlers/ad_data_handler.go
package handlers

import (
    "github.com/gin-gonic/gin"
    "platform/internal/addata"
    "platform/pkg/response"
    "net/http"
)

type AdDataHandler struct {
    service *addata.Service
}

func NewAdDataHandler(service *addata.Service) *AdDataHandler {
    return &AdDataHandler{service: service}
}

// ListAdData 获取广告数据列表
// GET /api/v1/ad-data
func (h *AdDataHandler) ListAdData(c *gin.Context) {
    var req addata.ListRequest
    if err := c.ShouldBindQuery(&req); err != nil {
        c.JSON(http.StatusBadRequest, response.Error(400, err.Error()))
        return
    }
    
    data, total, err := h.service.List(c.Request.Context(), &req)
    if err != nil {
        c.JSON(http.StatusInternalServerError, response.Error(500, "查询失败"))
        return
    }
    
    c.JSON(http.StatusOK, response.Success(gin.H{
        "items": data,
        "total": total,
    }))
}

// GetAdData 获取广告数据详情
// GET /api/v1/ad-data/:id
func (h *AdDataHandler) GetAdData(c *gin.Context) {
    id := c.Param("id")
    
    data, err := h.service.GetByID(c.Request.Context(), id)
    if err != nil {
        c.JSON(http.StatusNotFound, response.Error(404, "数据不存在"))
        return
    }
    
    c.JSON(http.StatusOK, response.Success(data))
}

// CreateAdData 创建广告数据
// POST /api/v1/ad-data
func (h *AdDataHandler) CreateAdData(c *gin.Context) {
    var req addata.CreateRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, response.Error(400, err.Error()))
        return
    }
    
    data, err := h.service.Create(c.Request.Context(), &req)
    if err != nil {
        c.JSON(http.StatusInternalServerError, response.Error(500, "创建失败"))
        return
    }
    
    c.JSON(http.StatusCreated, response.Success(data))
}
```

---

## 🔐 核心模块实现

### 1. JWT 认证 (RS256)

```go
// internal/security/jwt.go
package security

import (
    "crypto/rsa"
    "github.com/golang-jwt/jwt/v5"
    "time"
)

type JWTManager struct {
    privateKey *rsa.PrivateKey
    publicKey  *rsa.PublicKey
    expireMin  int
}

type Claims struct {
    UserID   uint   `json:"user_id"`
    Username string `json:"username"`
    Role     string `json:"role"`
    jwt.RegisteredClaims
}

func NewJWTManager(privateKeyPath, publicKeyPath string, expireMin int) (*JWTManager, error) {
    // 加载 RSA 密钥
    privateKey, err := loadPrivateKey(privateKeyPath)
    if err != nil {
        return nil, err
    }
    
    publicKey, err := loadPublicKey(publicKeyPath)
    if err != nil {
        return nil, err
    }
    
    return &JWTManager{
        privateKey: privateKey,
        publicKey:  publicKey,
        expireMin:  expireMin,
    }, nil
}

func (m *JWTManager) GenerateToken(userID uint, username, role string) (string, error) {
    claims := Claims{
        UserID:   userID,
        Username: username,
        Role:     role,
        RegisteredClaims: jwt.RegisteredClaims{
            ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Duration(m.expireMin) * time.Minute)),
            IssuedAt:  jwt.NewNumericDate(time.Now()),
        },
    }
    
    token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
    return token.SignedString(m.privateKey)
}

func (m *JWTManager) VerifyToken(tokenString string) (*Claims, error) {
    token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
        return m.publicKey, nil
    })
    
    if err != nil {
        return nil, err
    }
    
    claims, ok := token.Claims.(*Claims)
    if !ok || !token.Valid {
        return nil, fmt.Errorf("invalid token")
    }
    
    return claims, nil
}
```

### 2. 密码加密 (bcrypt)

```go
// internal/security/password.go
package security

import (
    "golang.org/x/crypto/bcrypt"
)

// HashPassword 使用 bcrypt 加密密码
func HashPassword(password string) (string, error) {
    bytes, err := bcrypt.GenerateFromPassword([]byte(password), 12)
    return string(bytes), err
}

// CheckPassword 验证密码
func CheckPassword(password, hash string) bool {
    err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
    return err == nil
}
```

### 3. Facebook 像素上报

```go
// internal/facebook/pixel.go
package facebook

import (
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "net/http"
    "time"
)

type PixelClient struct {
    pixelID     string
    accessToken string
    apiVersion  string
    httpClient  *http.Client
}

type PixelEvent struct {
    EventName    string                 `json:"event_name"`
    EventTime    int64                  `json:"event_time"`
    ActionSource string                 `json:"action_source"`
    EventID      string                 `json:"event_id"`
    UserData     PixelUserData          `json:"user_data"`
    CustomData   PixelCustomData        `json:"custom_data"`
}

type PixelUserData struct {
    Email       string `json:"em,omitempty"`
    Phone       string `json:"ph,omitempty"`
    IPAddress   string `json:"client_ip_address,omitempty"`
    UserAgent   string `json:"client_user_agent,omitempty"`
}

type PixelCustomData struct {
    Currency string  `json:"currency"`
    Value    float64 `json:"value"`
}

func NewPixelClient(pixelID, accessToken, apiVersion string) *PixelClient {
    return &PixelClient{
        pixelID:     pixelID,
        accessToken: accessToken,
        apiVersion:  apiVersion,
        httpClient:  &http.Client{Timeout: 30 * time.Second},
    }
}

// HashSHA256 哈希用户数据
func HashSHA256(value string) string {
    hash := sha256.Sum256([]byte(value))
    return hex.EncodeToString(hash[:])
}

// ReportPurchase 上报购买事件
func (c *PixelClient) ReportPurchase(eventID, email, phone, ip, ua string, value float64) error {
    event := PixelEvent{
        EventName:    "Purchase",
        EventTime:    time.Now().Unix(),
        ActionSource: "website",
        EventID:      eventID,
        UserData: PixelUserData{
            Email:     HashSHA256(email),
            Phone:     HashSHA256(phone),
            IPAddress: ip,
            UserAgent: ua,
        },
        CustomData: PixelCustomData{
            Currency: "USD",
            Value:    value,
        },
    }
    
    url := fmt.Sprintf("https://graph.facebook.com/%s/%s/events?access_token=%s",
        c.apiVersion, c.pixelID, c.accessToken)
    
    payload := map[string]interface{}{
        "data": []PixelEvent{event},
        "test": false,
    }
    
    jsonData, _ := json.Marshal(payload)
    resp, err := c.httpClient.Post(url, "application/json", bytes.NewBuffer(jsonData))
    if err != nil {
        return err
    }
    defer resp.Body.Close()
    
    if resp.StatusCode != http.StatusOK {
        return fmt.Errorf("facebook api error: %d", resp.StatusCode)
    }
    
    return nil
}
```

### 4. Postback 处理器

```go
// internal/postback/processor.go
package postback

import (
    "context"
    "errors"
    "gorm.io/gorm"
    "platform/internal/models"
    "platform/pkg/database"
    "go.uber.org/zap"
)

type Processor struct {
    db     *database.MySQL
    logger *zap.Logger
    forwarder *Forwarder
    notifier  *Notifier
}

func NewProcessor(db *database.MySQL, logger *zap.Logger, forwarder *Forwarder, notifier *Notifier) *Processor {
    return &Processor{
        db:       db,
        logger:   logger,
        forwarder: forwarder,
        notifier:  notifier,
    }
}

// ProcessConversion 处理转化
func (p *Processor) ProcessConversion(ctx context.Context, req *ConversionRequest) error {
    // 1. IP 白名单验证
    if err := p.validateIP(req.IPAddress); err != nil {
        return err
    }
    
    // 2. 数据格式验证
    if err := p.validateData(req); err != nil {
        return err
    }
    
    // 3. Click ID 关联
    click, err := p.associateClick(ctx, req.ClickID)
    if err != nil {
        return err
    }
    
    // 4. 重复检测
    exists, err := p.checkDuplicate(ctx, req.EventID)
    if err != nil {
        return err
    }
    if exists {
        return errors.New("duplicate conversion")
    }
    
    // 5. Cap 限制检查
    if err := p.checkCap(ctx, click.OfferID); err != nil {
        return err
    }
    
    // 6. 扣量计算
    originalPayout := click.Payout
    deductedPayout, rate := p.calculateDeduction(click.OfferID, originalPayout)
    
    // 7. 保存转化记录
    conversion := &models.PostbackConversion{
        ClickID:        req.ClickID,
        EventID:        req.EventID,
        ProductID:      click.ProductID,
        OriginalPayout: originalPayout,
        DeductedPayout: deductedPayout,
        DeductionRate:  rate,
        Status:         models.StatusApproved,
        IPAddress:      req.IPAddress,
        UserAgent:      req.UserAgent,
    }
    
    if err := p.db.WithContext(ctx).Create(conversion).Error; err != nil {
        return err
    }
    
    // 8. 转发到广告主 (异步)
    go p.forwarder.Forward(ctx, conversion)
    
    // 9. 发送通知 (异步)
    go p.notifier.Notify(ctx, conversion)
    
    p.logger.Info("conversion processed",
        zap.String("click_id", req.ClickID),
        zap.Float64("payout", deductedPayout))
    
    return nil
}
```

---

## 📋 重构阶段计划

### 第一阶段：基础框架 (2-3 周) ⭐⭐⭐

**目标：** 搭建 Go 项目骨架，实现核心功能

**任务清单：**

| 周 | 任务 | 交付物 |
|----|------|--------|
| 1 | 项目初始化 + 数据库模型 | go.mod, models/*.go |
| 1 | 数据库连接 + 配置管理 | pkg/database/, pkg/config/ |
| 1 | JWT 认证 + 用户登录 | internal/security/, api/handlers/auth_handler.go |
| 2 | 广告数据 CRUD API | api/handlers/ad_data_handler.go, internal/addata/ |
| 2 | 客户和产品管理 API | api/handlers/client_handler.go, internal/client/ |
| 3 | 前端联调 + 测试 | API 文档，单元测试 |

**验收标准：**
- ✅ 用户可以登录
- ✅ 广告数据可以 CRUD
- ✅ 前端可以正常访问

---

### 第二阶段：业务功能 (2-3 周) ⭐⭐

**目标：** 实现 Postback 和 Facebook 上报

**任务清单：**

| 周 | 任务 | 交付物 |
|----|------|--------|
| 4 | Postback 接收 + 验证 | internal/postback/ |
| 4 | Click 关联 + 重复检测 | internal/postback/click_associator.go |
| 5 | Cap 检查 + 扣量计算 | internal/postback/cap_checker.go, discount.go |
| 5 | 转发器实现 | internal/postback/forwarder.go |
| 6 | Facebook 像素上报 | internal/facebook/pixel.go |
| 6 | Telegram 通知 | internal/telegram/bot.go |

**验收标准：**
- ✅ Postback 可以正常接收和处理
- ✅ Facebook 事件可以上报
- ✅ Telegram 通知正常发送

---

### 第三阶段：辅助功能 (1-2 周) ⭐

**目标：** 完善定时任务、审计日志等

**任务清单：**

| 周 | 任务 | 交付物 |
|----|------|--------|
| 7 | 定时任务系统 | internal/scheduler/cron.go |
| 7 | 数据同步任务 | internal/scheduler/tasks.go |
| 8 | 审计日志系统 | internal/audit/logger.go |
| 8 | 性能优化 + 部署 | Dockerfile, systemd 配置 |

**验收标准：**
- ✅ 定时任务正常运行
- ✅ 审计日志完整记录
- ✅ 生产环境部署成功

---

## 🚀 部署配置

### Systemd 服务

```ini
# /etc/systemd/system/platform.service
[Unit]
Description=CPL Platform (Go)
After=network.target mysql.service redis.service

[Service]
Type=simple
User=platform
Group=platform
WorkingDirectory=/data/Platform
ExecStart=/data/Platform/bin/platform-server
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

# 环境变量
Environment="GIN_MODE=release"
Environment="TZ=Asia/Shanghai"

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=platform

[Install]
WantedBy=multi-user.target
```

### Docker 配置

```dockerfile
# deploy/Dockerfile
FROM golang:1.21-alpine AS builder

WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o platform-server ./cmd/server

FROM alpine:latest

RUN apk --no-cache add ca-certificates tzdata

WORKDIR /app
COPY --from=builder /build/platform-server .
COPY --from=builder /build/configs/config.yaml ./configs/

EXPOSE 8080

CMD ["./platform-server"]
```

---

## 📊 性能对比预估

| 指标 | Python (当前) | Go (预期) | 改善 |
|------|--------------|-----------|------|
| 启动时间 | 5 秒 | 0.5 秒 | 10x |
| 内存占用 | 300MB | 50MB | 6x |
| QPS (单核) | 500 | 2000 | 4x |
| 并发连接 | 1000 | 10000 | 10x |
| GC 停顿 | N/A | <1ms | - |
| 二进制大小 | N/A | ~20MB | - |

---

## ✅ 重构检查清单

### 代码质量

- [ ] 所有模型实现 `TableName()` 方法
- [ ] 所有 Handler 有错误处理
- [ ] 所有数据库操作有事务支持
- [ ] 所有外部调用有超时控制
- [ ] 所有敏感数据有日志脱敏

### 安全

- [ ] JWT 使用 RS256 算法
- [ ] 密码使用 bcrypt 加密
- [ ] SQL 注入防护 (GORM 参数化)
- [ ] XSS 防护 (输出转义)
- [ ] CORS 正确配置
- [ ] API 限流实现

### 性能

- [ ] 数据库连接池配置合理
- [ ] Redis 缓存使用得当
- [ ] 热点数据有缓存
- [ ] 慢查询有索引优化
- [ ] 日志异步写入

### 监控

- [ ] 健康检查端点 `/health`
- [ ] 指标暴露 `/metrics` (Prometheus)
- [ ] 结构化日志 (JSON 格式)
- [ ] 错误追踪 (Sentry/自建)
- [ ] 告警通知 (Telegram)

---

## 📝 总结

### 重构优势

| 方面 | 优势 |
|------|------|
| **性能** | 4-10 倍提升 |
| **稳定性** | 类型安全，编译时检查 |
| **部署** | 单二进制，无需依赖 |
| **维护** | 代码量减少 60% |
| **并发** | Goroutine 原生支持 |

### 风险提示

| 风险 | 缓解措施 |
|------|----------|
| 学习曲线 | 参考 GoPlatform 代码 |
| 数据迁移 | 复用现有 MySQL，无需迁移 |
| 前端兼容 | API 路径和格式保持不变 |
| 并行开发 | 分阶段重构，逐步切换 |

### 成功标准

- ✅ 所有 API 功能正常
- ✅ 性能达到预期目标
- ✅ 前端无需修改
- ✅ 数据完整无损
- ✅ 监控告警完善

---

**开始时间：** 2026-04-10  
**预计完成：** 2026-05-30 (8 周)  
**负责人：** 钳钱 🦀💰

**Let's Go! 🚀**
