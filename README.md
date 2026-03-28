# FiForesight 📈

FiForesight is an AI-powered financial forecasting web application designed to help investors predict short-term market movements for stocks and ETFs (like the S&P 500 or VUSA). It leverages real-time financial data and predictive algorithms to provide expected high and low price ranges for the next 24-48 hours.

## 🚀 Current Features

- **Real-Time Data Integration:** Powered by the **Alpha Vantage API** for accurate market quotes.
- **Smart Forecasting:** Calculates predicted high and low ranges based on current price action and recent market volatility.
- **Trend Analysis:** Automatically identifies **Bullish** or **Bearish** trends based on previous closing prices.
- **Modern UI/UX:** Built with **Next.js 14**, **Tailwind CSS**, and **DaisyUI** for a clean, responsive, and professional financial dashboard.
- **Robust Error Handling:** Gracefully handles API rate limits (5 calls/min on free tier) and provides clear user feedback.

## 🛠️ Tech Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, DaisyUI
- **Backend:** Next.js Serverless Functions (API Routes)
- **Data Provider:** Alpha Vantage API
- **State Management:** React Hooks
- **Planned:** Supabase (Auth & Database), TensorFlow.js (Machine Learning)

## 📋 Project Roadmap (Backlog)

### 1. Data Enrichment & Technicals
- [ ] **Historical Time-Series:** Fetch 6-month data to provide deeper context for predictions.
- [ ] **Technical Indicators:** Implement RSI (Relative Strength Index) and MACD (Moving Average Convergence Divergence) calculations.
- [ ] **Moving Averages:** Add 20-day and 50-day SMA to identify structural market shifts.

### 2. Advanced Prediction Algorithms
- [ ] **Linear Regression:** Predict price trajectory for the next 5 days using momentum algorithms.
- [ ] **Support & Resistance:** Algorithmically identify key price floors and ceilings.
- [ ] **Confidence Intervals:** Refine ranges based on historical "Accuracy Score."

### 3. AI & Machine Learning Integration
- [ ] **TensorFlow.js (LSTM):** Train a Long Short-Term Memory model to recognize complex time-series patterns.
- [ ] **Sentiment Analysis:** Incorporate market news sentiment to adjust predictions.

### 4. User Experience & Visualization
- [ ] **Interactive Charts:** Integrate `Recharts` or `Lightweight Charts` to visualize price history and forecast zones.
- [ ] **Watchlists:** Allow authenticated users to save tickers to a personal dashboard via **Supabase**.
- [ ] **Price Alerts:** Browser notifications for predicted breakouts.

## ⚙️ Getting Started

### Prerequisites
- Node.js (Latest LTS)
- A free API Key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/FiForesight.git
   cd FiForesight/frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Set up Environment Variables:**
   Create a `.env.local` file in the `frontend` directory:
   ```env
   ALPHA_VANTAGE_API_KEY=YOUR_KEY_HERE
   ```

4. **Run the development server:**
   ```bash
   npm run dev
   ```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

---
*Disclaimer: This tool is for educational purposes only. Financial markets involve risk. Always perform your own due diligence before making investment decisions.*
