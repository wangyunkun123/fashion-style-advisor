# 女性风格库 Women's Style Library

为 Fashion Advisor 女性用户测试建立的风格百科库。50 个风格，11 个集群，六维分类体系。

> 最后更新: 2026-06-23

## 六维分类体系

每个风格通过 6 个维度描述：文化集群 / 时代 / 正式度 / 场景 / 美学 / **趋势分类**。

### 趋势分类（trend_category）

| 分类 | 标签 | 说明 | 数量 |
|------|------|------|------|
| 🔥 **流行趋势** | `popular_trend` | 社交媒体驱动，近5-10年兴起或爆发 | 31 |
| 🏛️ **经典风格** | `classic` | 深厚文化/历史根基，持续数十年 | 10 |
| 🎭 **小众领域** | `niche` | 亚文化驱动，非主流审美 | 9 |

分类标准：
- **流行趋势**：TikTok/小红书原生、-core 后缀、2020s 社交媒体驱动
- **经典风格**：pre-2005 起源、持续实践 20+ 年、品牌生态成熟
- **小众领域**：亚文化社群、非商业主流、edgy_alternative 集群

边界案例：老钱风（TikTok 标签 + 百年美学 → 经典）、暗黑学院（TikTok 峰值 → 小众稳定态 → 小众）、Royalcore（TikTok 包装 → 趋势）

## 集群与风格

### 🈶 东亚风格（`_shared/east_asian.md`）
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-02 | 韩系少女 | Korean Girlie | 甜酷、Oversize、A字裙、K-pop |
| WF-03 | 日系森系 | Mori Kei | 自然面料、层叠、大地色、反时尚 |
| WF-04 | 新中式 | New Chinese | 盘扣/立领、丝绸、文化自信、混搭 |
| WF-44 | 日系阿美咔叽 | J-Amekaji | 原牛、工装、Red Wing、日式美式复古 |

### 🏰 欧洲经典（`_shared/european_classic.md`）
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-01 | 法式慵懒 | French Effortless | 不费力、条纹衫、中性色、红唇 |
| WF-06 | 极简 | Minimalist | 少即是多、建筑感、无Logo、面料至上 |
| WF-07 | 学院风 | Preppy | 常春藤、格子裙、牛津衬衫、乐福鞋 |
| WF-09 | 波西米亚 | Boho | 印花长裙、流苏/刺绣、反主流、音乐节 |
| WF-12 | 暗黑学院 | Dark Academia | 哥特浪漫、呢料/羊毛、高领叠穿、忧郁学者 |
| WF-34 | 巴黎 Chic | Parisian Chic | 粗花呢、小黑裙、珍珠、Chanel |
| WF-35 | 意式风情 | Italian Donna | 印花、金色首饰、墨镜、曲线 |
| WF-43 | 英伦淑女 | British Lady | 风衣、粗花呢、珍珠耳环、下午茶 |
| WF-48 | 马术优雅 | Equestrian | 马术靴、骑兵夹克、粗花呢、马衔扣 |

### 🌆 现代都市（`_shared/modern_urban.md`）
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-05 | 美式休闲 | American Casual | 丹宁、白T、帆布鞋、实用主义 |
| WF-08 | 运动休闲 | Athleisure | 瑜伽裤、Leggings、科技面料、舒适 |
| WF-10 | Y2K 千禧复古 | Y2K Revival | 低腰、闪亮/金属、Baby Tee、厚底鞋 |
| WF-11 | 都市通勤 | City Girl | 西装外套、阔腿裤、真丝衬衫、职场 |
| WF-33 | 户外机能 | Gorpcore | 冲锋衣、Salomon、工装裤、Gore-Tex |
| WF-36 | 北欧冷淡 | Scandi Cool | 建筑廓形、中性色、可持续、Hygge |
| WF-38 | 网球名媛 | Tenniscore | 百褶裙、Polo衫、白色、俱乐部 |

### 💕 浪漫少女
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-13 | 田园牧歌 | Cottagecore | 碎花、泡泡袖、钩针、野花草地 |
| WF-14 | 芭蕾风 | Balletcore | 裹身针织、纱裙、芭蕾平底鞋、缎面 |
| WF-15 | 甜媚少女 | Coquette | 蝴蝶结、蕾丝、珍珠、洛可可 |
| WF-16 | 软妹风 | Soft Girl | 粉彩、百褶裙、紧身针织、厚底鞋 |
| WF-40 | 浪漫歌剧 | Romantic Opera | 歌剧手套、丝绒斗篷、珍珠、剧院红 |
| WF-46 | 人鱼梦境 | Mermaidcore | 珠光、鳞片、鱼尾裙、贝壳 |

### 💎 奢华极简
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-17 | 静奢风 | Quiet Luxury | 无Logo、顶级面料、羊绒、不炫耀 |
| WF-18 | 老钱风 | Old Money | 绞花毛衣、珍珠项链、乐福鞋、传承 |
| WF-19 | 干净女孩 | Clean Girl | 紧贴发髻、金色耳环、水光肌、普拉提 |
| WF-47 | 香草女孩 | Vanilla Girl | 奶油白、羊毛开衫、暖金色、热可可 |

### 🌿 自然田园
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-20 | 海岸祖母 | Coastal Grandmother | 亚麻、宽腿白裤、草编包、海滩 |
| WF-21 | 地中海番茄 | Tomato Girl | 番茄红、白亚麻、草编鞋、南意大利 |
| WF-22 | 田园草地 | Meadowcore | 褪色碎花、鼠尾草绿、朦胧、野花 |
| WF-37 | 度假逃逸 | Resort Escape | 亚麻长裙、宽檐帽、细带凉鞋、热带 |

### 🎸 另类酷感
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-23 | 软垃圾摇滚 | Soft Grunge | 格纹衬衫、做旧、军靴、暗色花卉 |
| WF-24 | 独立颓废 | Indie Sleaze | 乐队T恤、紧身牛仔、烟熏妆、闪光摄影 |
| WF-25 | 都市酷感 | Downtown Cool | 皮夹克、单色调、大墨镜、建筑感 |
| WF-26 | 仙女垃圾 | Fairy Grunge | 暗色花卉、蕾丝、苔藓绿、森林妖精 |
| WF-42 | 摇滚 Chic | Rock Chic | 皮夹克、紧身牛仔、踝靴、乐队T恤 |

### 🏙️ 都市街头
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-27 | 运动少女混搭 | Blokette | 足球球衣、百褶裙、Samba、看台 |
| WF-28 | 女性街头 | Streetwear Women | 大号帽衫、限量球鞋、Logo、嘻哈 |
| WF-29 | 90年代复古 | Vintage 90s | 吊带裙、直筒牛仔、细带凉鞋、极简 |
| WF-39 | 嘻哈华丽 | Hip Hop Glam | 大号金链、运动套装、球鞋、皮草 |
| WF-45 | 西部女郎 | Western Babe | 牛仔靴、牛仔帽、流苏、绿松石 |

### 🎭 戏剧张力
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-30 | 黑帮大嫂 | Mob Wife | 人造皮草、豹纹、金饰、大墨镜 |
| WF-31 | 暗黑女性力 | Dark Feminine | 收腰西装、束身胸衣、宝石色调、丝绒 |
| WF-32 | 皇室浪漫 | Royalcore | 束身胸衣、丝绒、珍珠、蓬裙 |
| WF-41 | 办公室海妖 | Office Siren | 收腰西装、铅笔裙、尖头鞋、无框眼镜 |

### 🌍 文化优雅
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-49 | 端庄优雅 | Modest Chic | 长袖、高领、及踝长裙、层叠、自主选择 |

### 🚀 未来先锋
| ID | 名称 | 英文 | 核心关键词 |
|----|------|------|-----------|
| WF-50 | Y3K 未来感 | Cyber Y3K | 金属面料、外星墨镜、解构、3D打印 |

## 目录结构

```
styles_women/
├── README.md
├── categories.json                # 50风格注册表 + 11集群 + 六维分类
├── _shared/                       # 共享知识层
│   ├── east_asian.md
│   ├── european_classic.md
│   └── modern_urban.md
├── WF-01_french_effortless/
│   ├── encyclopedia.md            # 完整百科（9章节）
│   ├── fingerprint.json           # 评分指纹
│   ├── representative.jpg         # 封面图
│   ├── images/                    # 参考图片
│   └── references/                # 来源资料
├── ...
└── WF-50_cyber_y3k/
```

## 研究工作流

```bash
# 查看集群覆盖
python3 tools/style_research_agent.py --list-clusters

# 研究单个风格
python3 tools/style_research_agent.py WF-01

# 批量生成
python3 tools/style_research_agent.py --batch-female
```

## 进度

- [x] 50 个 encyclopedia.md（完整百科内容）✅ 2026-06-23
- [x] 50 个 representative.jpg（风格代表图封面）✅ 2026-06-23
- [x] 50 风格 categories.json 注册表（11 集群 + 六维分类）✅ 2026-06-23
- [x] 12 个 fingerprint.json（评分指纹——WF-01~WF-12）✅ 2026-06-23
- [ ] 38 个 fingerprint.json（WF-13~WF-50 扩展指纹，使之参与匹配引擎）
- [ ] 38 个 images/ 目录填充（参考图片）
- [ ] 社区内容章节（小红书+Instagram，后续按需补充）
