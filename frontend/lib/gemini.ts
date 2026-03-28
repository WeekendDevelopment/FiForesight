import { GoogleGenerativeAI } from '@google/generative-ai';

const genAI = new GoogleGenerativeAI(process.env.GOOGLE_GENAI_API_KEY || '');

/**
 * Generates a financial prediction and analyst note using your available Gemini model.
 */
export async function generatePrediction(
  symbol: string,
  priceHistory: any[],
  earningsHistory: any[],
  rsi: number
) {
  const priceContext = priceHistory.slice(-20).map(p => 
    `Date: ${new Date(p._time).toLocaleDateString()}, Close: ${p.close}`
  ).join('\n');

  const earningsContext = earningsHistory.slice(-8).map(e => 
    `Date: ${new Date(e._time).toLocaleDateString()}, Surprise: ${e.surprise}%`
  ).join('\n');

  const prompt = `
    System: You are a Senior Financial Quantitative Analyst. 
    Analyze the following data for ${symbol} and provide a 48-hour price prediction.

    Current context:
    - Symbol: ${symbol}
    - Current RSI: ${rsi.toFixed(2)}
    
    Recent Price History:
    ${priceContext}

    Recent Earnings Surprises:
    ${earningsContext}

    Your Task:
    1. Identify correlations between historical earnings surprises and price movements.
    2. Analyze the current momentum based on RSI.
    3. Provide a predicted High and Low range for the next 48 hours.
    4. Write a concise "Analyst Note" (max 3 sentences) explaining your reasoning.

    Output format (JSON only):
    {
      "predictedHigh": "number",
      "predictedLow": "number",
      "analystNote": "string",
      "confidence": "low|medium|high"
    }
  `;

  // 1. Try Gemini 2.5 Flash (Experimental)
  try {
    const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
    const result = await model.generateContent(prompt);
    const text = result.response.text();
    console.log('✅ Success: Used Gemini 2.5 Flash');
    return JSON.parse(text.replace(/```json|```/g, '').trim());
  } catch (error) {
    console.warn('⚠️ Gemini 2.5 Flash unavailable, trying 1.5 Flash...');
    
    // 2. Try Gemini 1.5 Flash (Stable Free Tier)
    try {
      const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });
      const result = await model.generateContent(prompt);
      const text = result.response.text();
      console.log('✅ Success: Used Gemini 1.5 Flash');
      return JSON.parse(text.replace(/```json|```/g, '').trim());
    } catch (fallbackError) {
      console.error('❌ All Gemini models failed.');
      const lastPrice = priceHistory[priceHistory.length - 1]?.close || 100;
      return {
        predictedHigh: (lastPrice * 1.01).toFixed(2),
        predictedLow: (lastPrice * 0.99).toFixed(2),
        analystNote: "AI analysis currently unavailable. Using technical fallback.",
        confidence: "low"
      };
    }
  }
}
