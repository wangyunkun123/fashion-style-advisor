#!/usr/bin/env python3
"""
精准天气顾问 — 定位+实时天气+穿搭建议
用法:
  python3 tools/weather_advisor.py                    # 输出当前天气详情
  python3 tools/weather_advisor.py --json              # JSON格式
"""

import json, urllib.request, urllib.parse, re

# 用户位置配置
LOCATION = {
    'city': 'Beijing',
    'district': 'Chaoyang',  # 朝阳区
    'lat': '39.9042',
    'lon': '116.4074',
}

def fetch_weather(location='Beijing'):
    """从 wttr.in 获取详细天气"""
    url = f'https://wttr.in/{location}?format=j1&lang=zh'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'FashionStyleAdvisor/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"⚠️ 天气获取失败: {e}")
        return None


# 天气描述中英映射 + 对应图标
WEATHER_MAP = {
    'sunny': ('晴', '☀️'), 'clear': ('晴', '☀️'),
    'partly cloudy': ('多云', '⛅'), 'cloudy': ('阴', '☁️'),
    'overcast': ('阴', '☁️'), 'mist': ('雾', '🌫️'), 'fog': ('雾', '🌫️'),
    'haze': ('霾', '🌫️'), 'smoky': ('霾', '🌫️'),
    'rain': ('雨', '🌧️'), 'light rain': ('小雨', '🌦️'),
    'moderate rain': ('中雨', '🌧️'), 'heavy rain': ('大雨', '🌧️'),
    'thunderstorm': ('雷暴', '⛈️'), 'rain with thunderstorm': ('雷暴', '⛈️'),
    'thunder': ('雷暴', '⛈️'),
    'snow': ('雪', '❄️'), 'light snow': ('小雪', '🌨️'),
    'heavy snow': ('大雪', '❄️'), 'sleet': ('雨夹雪', '🌨️'),
    'drizzle': ('毛毛雨', '🌦️'),
    'wind': ('大风', '💨'), 'windy': ('大风', '💨'),
    'hot': ('炎热', '🔥'), 'cold': ('寒冷', '🥶'),
}


def translate_weather(desc_en):
    """翻译天气描述 + 返回对应图标"""
    key = desc_en.lower().strip()
    if key in WEATHER_MAP:
        return WEATHER_MAP[key]
    # 模糊匹配
    for k, v in WEATHER_MAP.items():
        if k in key:
            return v
    return (desc_en, '🌤')


def analyze_weather(data):
    """分析天气数据，返回穿搭相关建议"""
    if not data:
        return None

    current = data.get('current_condition', [{}])[0]
    forecast = data.get('weather', [{}])[0]

    temp = int(current.get('temp_C', 25))
    humidity = int(current.get('humidity', 50))
    wind_speed = int(current.get('windspeedKmph', 10))
    desc_en = current.get('weatherDesc', [{}])[0].get('value', 'Clear')
    weather_zh, weather_icon = translate_weather(desc_en)
    precipitation = float(current.get('precipMM', 0))
    uv_index = int(current.get('uvIndex', 3))

    # 今天预报
    max_temp = int(forecast.get('maxtempC', temp + 5))
    min_temp = int(forecast.get('mintempC', temp - 5))
    hourly = forecast.get('hourly', [])

    # 天气风险评级
    risks = []
    if precipitation > 1.0:
        risks.append({'level': 'rain', 'label': '降水', 'advice': '防水外套+深色裤装+防滑鞋'})
    if wind_speed > 30:
        risks.append({'level': 'wind', 'label': '大风', 'advice': '防风外套+避免宽松帽子'})
    if temp > 35:
        risks.append({'level': 'heat', 'label': '高温', 'advice': '轻薄透气面料+防晒帽+墨镜'})
    if temp < 10:
        risks.append({'level': 'cold', 'label': '低温', 'advice': '多层叠穿+保暖外套+围巾手套'})
    if humidity > 80 and temp > 25:
        risks.append({'level': 'humid', 'label': '闷热', 'advice': '速干面料+宽松剪裁+浅色系'})
    if any(kw in weather_zh for kw in ['雨', '雪', '雷', '暴']):
        risks.append({'level': 'rain', 'label': weather_zh, 'advice': '防水外套+深色下装+防滑鞋底'})

    # 日内天气变化检测
    volatile = False
    if hourly:
        conditions = set()
        for h in hourly[:12]:
            desc = h.get('weatherDesc', [{}])[0].get('value', '')
            conditions.add(desc)
        volatile = len(conditions) >= 3  # 半天内3种以上天气=多变

    return {
        'current': {'temp': temp, 'humidity': humidity, 'wind': wind_speed,
                    'desc': weather_zh, 'icon': weather_icon, 'precip': precipitation, 'uv': uv_index},
        'forecast': {'max': max_temp, 'min': min_temp},
        'risks': risks,
        'volatile': volatile,
        'summary': f'{weather_zh} {temp}°C 湿度{humidity}%',
    }


def weather_line(analysis):
    """生成推送用的天气行"""
    if not analysis:
        return ''
    c = analysis['current']
    f = analysis['forecast']
    parts = [f"{c.get('icon', '🌤')} {c['desc']} {c['temp']}°C (↓{f['min']}°C ↑{f['max']}°C)"]
    if c['wind'] > 20:
        parts.append(f"💨 风力{c['wind']}km/h")
    if c['humidity'] > 75:
        parts.append(f"💧 湿度{c['humidity']}%")
    return ' · '.join(parts)


def weather_advice(analysis):
    """生成天气应对建议"""
    if not analysis:
        return []
    advice = []
    for r in analysis.get('risks', []):
        advice.append(f"⚠️ {r['label']}预警：{r['advice']}")
    if analysis.get('volatile'):
        advice.append('🌪 今日天气多变，建议准备备用穿搭方案')
    return advice


def main():
    data = fetch_weather(LOCATION['city'])
    analysis = analyze_weather(data)

    if '--json' in sys.argv:
        import sys
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
        return

    if analysis:
        print(weather_line(analysis))
        for a in weather_advice(analysis):
            print(a)
    else:
        print("❌ 无法获取天气")


if __name__ == '__main__':
    import sys
    main()
