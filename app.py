from flask import Flask, jsonify, request
from flask_cors import CORS
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import ta
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Initialiser TvDatafeed (anonyme, pas besoin de compte)
tv = TvDatafeed()

# Mapping des intervalles
INTERVALS = {
    '1min': Interval.in_1_minute,
    '5min': Interval.in_5_minute,
    '15min': Interval.in_15_minute,
    '30min': Interval.in_30_minute,
    '1h': Interval.in_1_hour,
    '2h': Interval.in_2_hour,
    '4h': Interval.in_4_hour,
    '1D': Interval.in_daily,
    '1W': Interval.in_weekly,
}

# Configuration des symboles
SYMBOLS = {
    'XAUUSD': {'exchange': 'OANDA', 'symbol': 'XAUUSD'},
    'XAGUSD': {'exchange': 'OANDA', 'symbol': 'XAGUSD'},
    'DXY': {'exchange': 'TVC', 'symbol': 'DXY'},
}

def calculate_indicators(df):
    """Calcule tous les indicateurs techniques"""
    
    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    
    # MACD
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    
    # Bollinger Bands
    bollinger = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'] = bollinger.bollinger_hband()
    df['bb_middle'] = bollinger.bollinger_mavg()
    df['bb_lower'] = bollinger.bollinger_lband()
    
    # ATR (Average True Range)
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    
    # Stochastic
    stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    
    # EMAs
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    df['ema_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
    
    # Support et Résistance (max/min sur 50 périodes)
    df['resistance'] = df['high'].rolling(window=50).max()
    df['support'] = df['low'].rolling(window=50).min()
    
    return df

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/data', methods=['GET'])
def get_data():
    """
    Endpoint principal pour récupérer les données
    Params:
        - symbol: XAUUSD, XAGUSD, DXY
        - interval: 5min, 15min, 1h, 4h, 1D
        - bars: nombre de bougies (défaut: 100)
    """
    try:
        symbol = request.args.get('symbol', 'XAUUSD')
        interval = request.args.get('interval', '1h')
        bars = int(request.args.get('bars', 100))
        
        # Vérification
        if symbol not in SYMBOLS:
            return jsonify({'error': f'Symbol {symbol} not supported'}), 400
        
        if interval not in INTERVALS:
            return jsonify({'error': f'Interval {interval} not supported'}), 400
        
        # Récupérer les données
        config = SYMBOLS[symbol]
        df = tv.get_hist(
            symbol=config['symbol'],
            exchange=config['exchange'],
            interval=INTERVALS[interval],
            n_bars=bars
        )
        
        if df is None or df.empty:
            return jsonify({'error': 'No data received from TradingView'}), 500
        
        # Calculer les indicateurs
        df = calculate_indicators(df)
        
        # Préparer la réponse
        df_reset = df.reset_index()
        
        # Dernière bougie (prix actuel)
        current = df_reset.iloc[-1]
        previous = df_reset.iloc[-2]
        
        # Analyse de tendance
        trend = "NEUTRE"
        if current['close'] > current['ema_20'] > current['ema_50']:
            trend = "HAUSSIÈRE"
        elif current['close'] < current['ema_20'] < current['ema_50']:
            trend = "BAISSIÈRE"
        
        # Signal RSI
        rsi_signal = "NEUTRE"
        if current['rsi'] > 70:
            rsi_signal = "SURACHETÉ"
        elif current['rsi'] < 30:
            rsi_signal = "SURVENDU"
        
        # Signal MACD
        macd_signal = "NEUTRE"
        if current['macd'] > current['macd_signal']:
            macd_signal = "HAUSSIER"
        else:
            macd_signal = "BAISSIER"
        
        response = {
            'symbol': symbol,
            'interval': interval,
            'timestamp': current['datetime'].isoformat(),
            'prix_actuel': float(current['close']),
            'variation': float(current['close'] - previous['close']),
            'variation_pourcent': float(((current['close'] - previous['close']) / previous['close']) * 100),
            
            'indicateurs': {
                'rsi': float(current['rsi']),
                'rsi_signal': rsi_signal,
                'macd': float(current['macd']),
                'macd_signal': float(current['macd_signal']),
                'macd_diff': float(current['macd_diff']),
                'macd_signal_txt': macd_signal,
                'stoch_k': float(current['stoch_k']),
                'stoch_d': float(current['stoch_d']),
                'atr': float(current['atr']),
                'ema_20': float(current['ema_20']),
                'ema_50': float(current['ema_50']),
                'ema_200': float(current['ema_200']),
            },
            
            'bollinger': {
                'upper': float(current['bb_upper']),
                'middle': float(current['bb_middle']),
                'lower': float(current['bb_lower']),
                'position': 'proche_resistance' if current['close'] > current['bb_middle'] else 'proche_support'
            },
            
            'niveaux': {
                'resistance': float(current['resistance']),
                'support': float(current['support']),
                'distance_resistance': float(current['resistance'] - current['close']),
                'distance_support': float(current['close'] - current['support'])
            },
            
            'analyse': {
                'tendance': trend,
                'position_vs_ema20': 'AU-DESSUS' if current['close'] > current['ema_20'] else 'EN-DESSOUS',
                'force': 'FORTE' if abs(current['close'] - current['ema_20']) > current['atr'] else 'FAIBLE'
            },
            
            'donnees_brutes': df_reset.tail(10).to_dict('records')
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/multi', methods=['POST'])
def get_multi_data():
    """
    Endpoint pour récupérer plusieurs symboles et timeframes en une fois
    Body JSON:
    {
        "symbols": ["XAUUSD", "XAGUSD"],
        "intervals": ["5min", "1h", "4h", "1D"]
    }
    """
    try:
        data = request.get_json()
        symbols = data.get('symbols', ['XAUUSD'])
        intervals = data.get('intervals', ['1h'])
        
        results = {}
        
        for symbol in symbols:
            results[symbol] = {}
            for interval in intervals:
                # Appel interne
                req = type('obj', (object,), {'args': type('obj', (object,), {
                    'get': lambda k, d=None: {'symbol': symbol, 'interval': interval, 'bars': 100}.get(k, d)
                })()})()
                
                response = get_data()
                if response[1] == 200:  # Status code OK
                    results[symbol][interval] = response[0].get_json()
                else:
                    results[symbol][interval] = {'error': 'Failed to fetch'}
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
