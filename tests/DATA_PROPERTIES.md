# Propiedades esperables de los objetos de datos de BinPan

Documento de referencia para disenar tests. Define las invariantes, restricciones
y propiedades que deben cumplir los DataFrames que BinPan construye a partir de
la API de Binance.

---

## 1. Klines (velas OHLCV)

**Almacenado en**: `Symbol.df` (pd.DataFrame)

### 1.1 Columnas

| Columna | Tipo esperado | Nullable | Descripcion |
|---------|---------------|----------|-------------|
| `Open time` | object (str) | No | Fecha/hora apertura formateada con timezone |
| `Open` | float64 | No | Precio de apertura |
| `High` | float64 | No | Precio maximo |
| `Low` | float64 | No | Precio minimo |
| `Close` | float64 | No | Precio de cierre |
| `Volume` | float64 | No | Volumen en base asset |
| `Close time` | object (str) | No | Fecha/hora cierre formateada con timezone |
| `Quote volume` | float64 | No | Volumen en quote asset |
| `Trades` | int64 | No | Numero de trades en la vela |
| `Taker buy base volume` | float64 | No | Volumen taker comprador (base) |
| `Taker buy quote volume` | float64 | No | Volumen taker comprador (quote) |
| `Ignore` | float64 | Si | Campo ignorado por Binance (siempre 0) |
| `Open timestamp` | int64 | No | Timestamp apertura en ms (epoch UTC) |
| `Close timestamp` | int64 | No | Timestamp cierre en ms (epoch UTC) |

**Nota**: Las columnas de indicadores tecnicos se anaden dinamicamente (ej: `EMA_21`,
`RSI_14`, `Supertrend_10_3.0`). No forman parte del schema base.

### 1.2 Indice

| Propiedad | Valor esperado |
|-----------|---------------|
| Tipo | `pd.DatetimeIndex` |
| Timezone | La timezone solicitada (ej: `Europe/Madrid`, `UTC`) |
| Basado en | `Open timestamp` (ms convertido a datetime) |
| Nombre | `"{symbol} {tick_interval} {time_zone}"` (ej: `"BTCUSDT 15m Europe/Madrid"`) |
| Monotonicidad | **Estrictamente creciente** |
| Unicidad | **Unico** (no hay dos velas con el mismo Open time) |

### 1.3 Unicidad

| Campo de unicidad | Descripcion |
|-------------------|-------------|
| `Open timestamp` | Cada vela tiene un timestamp de apertura unico. Es la clave primaria natural. |

**Invariante**: `df['Open timestamp'].is_unique == True`

### 1.4 Continuidad temporal

Las klines deben ser **continuas**: el intervalo entre `Open timestamp` consecutivos
debe ser constante e igual al tick del intervalo.

| Propiedad | Formula |
|-----------|---------|
| Tick esperado (ms) | `KlineTimestamp(any_open_ts, interval).tick_ms` |
| Continuidad | `df['Open timestamp'].diff().dropna().unique() == [tick_ms]` |
| Sin huecos | No faltan velas intermedias en el rango temporal |

**Excepcion conocida**: Binance puede omitir velas en periodos sin actividad de trading
(muy raro en pares liquidos como BTCUSDT, mas comun en altcoins iliquidas). BinPan
tiene `check_continuity()` y `repair_kline_discontinuity()` en `auxiliar.py` para
detectar y rellenar estos huecos.

### 1.5 Restricciones de valores (invariantes OHLCV)

| Invariante | Expresion |
|------------|-----------|
| High es el maximo | `df['High'] >= df[['Open', 'Close']].max(axis=1)` |
| Low es el minimo | `df['Low'] <= df[['Open', 'Close']].min(axis=1)` |
| High >= Low | `df['High'] >= df['Low']` |
| Precios positivos | `df[['Open', 'High', 'Low', 'Close']] > 0` |
| Volumen no negativo | `df['Volume'] >= 0` |
| Quote volume no negativo | `df['Quote volume'] >= 0` |
| Trades no negativo | `df['Trades'] >= 0` |
| Taker <= Total (base) | `df['Taker buy base volume'] <= df['Volume']` |
| Taker <= Total (quote) | `df['Taker buy quote volume'] <= df['Quote volume']` |
| Close ts > Open ts | `df['Close timestamp'] > df['Open timestamp']` |
| Close ts = Open ts + tick - 1 | `df['Close timestamp'] == df['Open timestamp'] + tick_ms - 1` |

### 1.6 Relaciones temporales entre velas consecutivas

| Invariante | Expresion |
|------------|-----------|
| Open[n+1] = Open[n] + tick_ms | `df['Open timestamp'].diff().dropna() == tick_ms` |
| Close[n] < Open[n+1] | Sin solapamiento entre velas |
| Close[n] + 1 = Open[n+1] | Adyacencia exacta (close timestamp + 1ms = next open) |

### 1.7 Velas no cerradas

BinPan **descarta** la ultima vela si aun no ha cerrado. Solo se incluyen velas
completamente cerradas. Esto se verifica en `market.py` al obtener los datos.

**Invariante**: `df['Close timestamp'].iloc[-1] < now_server_ms()`

---

## 2. Aggregated Trades (aggTrades)

**Almacenado en**: `Symbol.trades` (pd.DataFrame) cuando se obtienen con `get_agg_trades()`

### 2.1 Columnas

| Columna | Tipo esperado | Nullable | Descripcion |
|---------|---------------|----------|-------------|
| `Aggregate tradeId` | int64 | No | ID unico del trade agregado |
| `Price` | float64 | No | Precio de ejecucion |
| `Quantity` | float64 | No | Cantidad en base asset |
| `First tradeId` | int64 | No | ID del primer trade atomico incluido |
| `Last tradeId` | int64 | No | ID del ultimo trade atomico incluido |
| `Date` | object (str) | No | Fecha formateada (sin timezone) |
| `Timestamp` | int64 | No | Timestamp en ms (epoch UTC) |
| `Buyer was maker` | bool | No | True si el comprador fue maker (la venta fue taker) |
| `Best price match` | bool | No | True si fue la mejor coincidencia de precio |

### 2.2 Indice

| Propiedad | Valor esperado |
|-----------|---------------|
| Tipo | `pd.DatetimeIndex` |
| Timezone | La timezone solicitada |
| Basado en | `Timestamp` (ms convertido a datetime) |
| Nombre | `"{symbol} {time_zone}"` |
| Monotonicidad | **Creciente** (no estrictamente: pueden haber trades en el mismo ms) |
| Unicidad | **NO unico** (multiples trades pueden compartir timestamp) |

### 2.3 Unicidad

| Campo de unicidad | Descripcion |
|-------------------|-------------|
| `Aggregate tradeId` | Cada aggTrade tiene un ID unico y secuencial. Es la clave primaria. |

**Invariante**: `df['Aggregate tradeId'].is_unique == True`

### 2.4 Secuencialidad de IDs

Los aggTrade IDs son **secuenciales y sin huecos** dentro de un mismo par:

| Invariante | Expresion |
|------------|-----------|
| IDs consecutivos | `df['Aggregate tradeId'].diff().dropna() == 1` |
| IDs crecientes | `df['Aggregate tradeId'].is_monotonic_increasing == True` |

### 2.5 Relacion First/Last tradeId

Cada aggTrade agrupa uno o mas trades atomicos contiguos:

| Invariante | Expresion |
|------------|-----------|
| First <= Last | `df['First tradeId'] <= df['Last tradeId']` |
| Sin solapamiento | `df['First tradeId'].iloc[n+1] == df['Last tradeId'].iloc[n] + 1` |
| Cobertura completa | Los rangos [First, Last] de aggTrades consecutivos son adyacentes |

### 2.6 Restricciones de valores

| Invariante | Expresion |
|------------|-----------|
| Precio positivo | `df['Price'] > 0` |
| Cantidad positiva | `df['Quantity'] > 0` |
| Timestamp creciente | `df['Timestamp'].is_monotonic_increasing == True` (no estricto) |
| IDs positivos | `df['Aggregate tradeId'] > 0` |

### 2.7 Ordenacion temporal

Los aggTrades estan ordenados por `Aggregate tradeId` (que es tambien orden temporal).
Dentro del mismo timestamp (ms), el orden lo da el ID.

**Invariante**: Si `Timestamp[n] == Timestamp[n+1]`, entonces `Aggregate tradeId[n] < Aggregate tradeId[n+1]`.

---

## 3. Atomic Trades (trades historicos)

**Almacenado en**: `Symbol.trades` (pd.DataFrame) cuando se obtienen con `get_atomic_trades()`

### 3.1 Columnas

| Columna | Tipo esperado | Nullable | Descripcion |
|---------|---------------|----------|-------------|
| `Trade Id` | int64 | No | ID unico del trade atomico |
| `Price` | float64 | No | Precio de ejecucion |
| `Quantity` | float64 | No | Cantidad en base asset |
| `Quote quantity` | float64 | No | Cantidad en quote asset (= Price * Quantity) |
| `Date` | object (str) | No | Fecha formateada (sin timezone) |
| `Timestamp` | int64 | No | Timestamp en ms (epoch UTC) |
| `Buyer was maker` | bool | No | True si el comprador fue maker |
| `Best price match` | bool | No | True si fue la mejor coincidencia de precio |

### 3.2 Indice

| Propiedad | Valor esperado |
|-----------|---------------|
| Tipo | `pd.DatetimeIndex` |
| Timezone | La timezone solicitada |
| Basado en | `Timestamp` (ms convertido a datetime) |
| Nombre | `"{symbol} {time_zone}"` |
| Monotonicidad | **Creciente** (no estrictamente: multiples trades en el mismo ms) |
| Unicidad | **NO unico** |

### 3.3 Unicidad

| Campo de unicidad | Descripcion |
|-------------------|-------------|
| `Trade Id` | Cada trade atomico tiene un ID unico y secuencial. Es la clave primaria. |

**Invariante**: `df['Trade Id'].is_unique == True`

### 3.4 Secuencialidad de IDs

| Invariante | Expresion |
|------------|-----------|
| IDs consecutivos | `df['Trade Id'].diff().dropna() == 1` |
| IDs crecientes | `df['Trade Id'].is_monotonic_increasing == True` |

### 3.5 Relacion Quote quantity

| Invariante | Expresion (aproximada) |
|------------|----------------------|
| Quote = Price * Qty | `abs(df['Quote quantity'] - df['Price'] * df['Quantity']) < epsilon` |

**Nota**: Puede haber diferencias minimas por redondeo de la API. Usar tolerancia
relativa (ej: `np.isclose` con `rtol=1e-6`).

### 3.6 Restricciones de valores

| Invariante | Expresion |
|------------|-----------|
| Precio positivo | `df['Price'] > 0` |
| Cantidad positiva | `df['Quantity'] > 0` |
| Quote positivo | `df['Quote quantity'] > 0` |
| Timestamp creciente | `df['Timestamp'].is_monotonic_increasing == True` (no estricto) |
| IDs positivos | `df['Trade Id'] > 0` |

### 3.7 Relacion con aggTrades

Un trade atomico pertenece exactamente a un aggTrade. Si se tienen ambos datasets
para el mismo rango:

| Invariante | Descripcion |
|------------|-------------|
| Cobertura de IDs | Cada `Trade Id` aparece en exactamente un rango `[First tradeId, Last tradeId]` de un aggTrade |
| Mismo precio | Todos los trades atomicos dentro de un aggTrade comparten el mismo `Price` |
| Suma de cantidades | `aggTrade['Quantity'] == sum(atomic['Quantity'])` para los trades en su rango |
| Mismo maker side | Todos los trades atomicos de un aggTrade comparten `Buyer was maker` |

---

## 4. Order Book (depth snapshot)

**Almacenado en**: `Symbol.orderbook` (pd.DataFrame)

### 4.1 Columnas

| Columna | Tipo esperado | Nullable | Descripcion |
|---------|---------------|----------|-------------|
| `Price` | float64 | No | Nivel de precio |
| `Quantity` | float64 | No | Cantidad ofertada/demandada |
| `Side` | object (str) | No | `'bid'` (compra) o `'ask'` (venta) |

### 4.2 Indice

| Propiedad | Valor esperado |
|-----------|---------------|
| Tipo | `RangeIndex` (0, 1, 2, ...) |
| Nombre | `"{symbol} updateId:{lastUpdateId}"` |

### 4.3 Unicidad

| Campo de unicidad | Descripcion |
|-------------------|-------------|
| `Price` por `Side` | Dentro de un mismo side, cada precio aparece una sola vez |

**Invariante**: No hay precios duplicados dentro de bids ni dentro de asks.

### 4.4 Ordenacion

| Invariante | Expresion |
|------------|-----------|
| Bids descendentes | Precios de bids ordenados de mayor a menor |
| Asks ascendentes | Precios de asks ordenados de menor a mayor |
| DataFrame completo | Ordenado por `Price` descendente (bids primero, luego asks) |

### 4.5 Restricciones de valores

| Invariante | Expresion |
|------------|-----------|
| Precios positivos | `df['Price'] > 0` |
| Cantidades positivas | `df['Quantity'] > 0` (niveles con qty 0 no se incluyen) |
| Side valido | `df['Side'].isin(['bid', 'ask'])` |
| Best bid > Best ask NO | El mejor bid puede ser >= best ask temporalmente (crossed book, raro) |
| Best bid < Best ask (normal) | `bids['Price'].max() < asks['Price'].min()` en condiciones normales |

### 4.6 Spread

| Propiedad | Formula |
|-----------|---------|
| Best bid | `df[df['Side'] == 'bid']['Price'].max()` |
| Best ask | `df[df['Side'] == 'ask']['Price'].min()` |
| Spread | `best_ask - best_bid` |
| Spread (%) | `(best_ask - best_bid) / best_bid * 100` |

**Invariante (condicion normal)**: `spread >= 0`

### 4.7 Respuesta cruda de la API (Binance depth endpoint)

```json
{
    "lastUpdateId": 1027024,
    "bids": [
        ["4.00000000", "431.00000000"],
        ["3.99999900", "500.00000000"]
    ],
    "asks": [
        ["4.00000200", "12.00000000"],
        ["4.00000300", "300.00000000"]
    ]
}
```

- `bids` y `asks` son listas de `[precio_str, cantidad_str]`
- Ordenados por la API: bids descendente, asks ascendente
- `lastUpdateId` identifica la version del snapshot (se usa en el nombre del indice)
- Limite maximo: 5000 niveles por side (BinPan pide 5000 por defecto)
- Niveles con cantidad 0 no se incluyen en la respuesta

---

## 5. Respuestas crudas de la API (referencia)

### 5.1 Kline (array de 12 elementos)

```json
[
  1499040000000,        // [0]  Open time (ms UTC)
  "0.01634790",         // [1]  Open (string)
  "0.80000000",         // [2]  High (string)
  "0.01575800",         // [3]  Low (string)
  "0.01577100",         // [4]  Close (string)
  "148976.11427815",    // [5]  Volume base asset (string)
  1499644799999,        // [6]  Close time (ms UTC)
  "2434.19055334",      // [7]  Quote asset volume (string)
  308,                  // [8]  Number of trades (int)
  "1756.87402397",      // [9]  Taker buy base volume (string)
  "28.46694368",        // [10] Taker buy quote volume (string)
  "17928899.62484339"   // [11] Ignore (string)
]
```

### 5.2 Aggregated Trade (dict)

```json
{
    "a": 26129,             // Aggregate tradeId
    "p": "0.01633102",      // Price (string)
    "q": "4.70443515",      // Quantity (string)
    "f": 27781,             // First tradeId (int)
    "l": 27781,             // Last tradeId (int)
    "T": 1498793709153,     // Timestamp ms (int)
    "m": true,              // Buyer was maker (bool)
    "M": true               // Best price match (bool)
}
```

### 5.3 Atomic Trade (dict)

```json
{
    "id": 28457,                // Trade Id (int)
    "price": "4.00000100",     // Price (string)
    "qty": "12.00000000",      // Quantity (string)
    "quoteQty": "48.000012",   // Quote quantity (string)
    "time": 1499865549590,     // Timestamp ms (int)
    "isBuyerMaker": true,      // Buyer was maker (bool)
    "isBestMatch": true        // Best price match (bool)
}
```

---

## 6. Propiedades transversales

### 6.1 Consistencia temporal klines-trades

Si se obtienen klines y trades para el mismo rango temporal:

| Invariante | Descripcion |
|------------|-------------|
| Precios dentro de rango | Cada `Price` de un trade dentro de una vela esta en `[Low, High]` |
| Volumen consistente | La suma de `Quantity` de trades en una vela == `Volume` de esa vela (approx) |
| Conteo de trades | El numero de trades atomicos en una vela == `Trades` de esa vela |

### 6.2 Markets soportados y diferencias entre ellos

Los datos pueden venir de 3 mercados. **Las klines son identicas** en estructura
(12 campos, misma semantica), pero **aggTrades y depth tienen diferencias**:

| Market | Ejemplo | Klines | AggTrades | Depth |
|--------|---------|--------|-----------|-------|
| `spot` | BTCUSDT | 12 campos | 8 keys: `a,p,q,f,l,T,m,M` | `bids,asks,lastUpdateId` |
| `um` | BTCUSDT (futures) | 12 campos (identico) | 8 keys: `a,p,q,nq,f,l,T,m` | + `E,T` |
| `cm` | BTCUSD_PERP | 12 campos (identico) | 7 keys: `a,p,q,f,l,T,m` | + `E,T,pair,symbol` |

#### Diferencias en aggTrades por market

| Campo | Spot | UM | CM | Descripcion |
|-------|------|----|----|-------------|
| `M` (Best price match) | Si | **No** | **No** | Solo existe en spot |
| `nq` (notional quantity) | No | **Si** | No | Cantidad nocional, solo en UM futures |

Esto implica que la columna `Best price match` puede estar **ausente** en
DataFrames de aggTrades de futuros. BinPan debe manejar esto (rellenar con
True o con NaN).

#### Diferencias en depth por market

| Campo | Spot | UM | CM | Descripcion |
|-------|------|----|----|-------------|
| `E` (event time) | No | Si | Si | Timestamp del evento |
| `T` (transaction time) | No | Si | Si | Timestamp de la transaccion |
| `pair` | No | No | Si | Par base (ej: "BTCUSD") |
| `symbol` | No | No | Si | Simbolo completo (ej: "BTCUSD_PERP") |

Los campos adicionales de futures (`E`, `T`, `pair`, `symbol`) no se usan
actualmente en el DataFrame de BinPan. Solo se usan `bids`, `asks` y
`lastUpdateId`, que estan presentes en los 3 mercados.

### 6.3 Intervalos validos para klines

```
1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w
```

**Nota**: El intervalo `1M` (mensual) **no esta soportado** por `kline-timestamp`.

### 6.4 Timestamps

| Propiedad | Valor |
|-----------|-------|
| Unidad | Milisegundos desde epoch (1970-01-01 00:00:00 UTC) |
| Precision | Milisegundos (entero, no float) |
| Rango valido | > 0 (post-epoch) |
| Referencia | Siempre UTC en la API; BinPan convierte a timezone del usuario para display |

---

## 7. Resumen de claves primarias y propiedades clave

| Objeto | Clave primaria | Continuidad | Ordenacion | Deduplicacion |
|--------|---------------|-------------|------------|---------------|
| Klines | `Open timestamp` | Temporal (tick fijo) | `Open timestamp` ASC | Por timestamp |
| AggTrades | `Aggregate tradeId` | IDs secuenciales | `Aggregate tradeId` ASC | Por ID |
| Atomic Trades | `Trade Id` | IDs secuenciales | `Trade Id` ASC | Por ID |
| Order Book | `(Price, Side)` | N/A (snapshot) | `Price` DESC | Por precio/side |
