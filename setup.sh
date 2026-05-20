#!/data/data/com.termux/files/usr/bin/bash
# Setup script for Option Analytics Backend on Termux

echo "=========================================="
echo "  OPTION ANALYTICS BACKEND SETUP"
echo "=========================================="

# Check if in Termux
if [ -z "$TERMUX_VERSION" ]; then
    echo "⚠️  Warning: Not running in Termux environment"
fi

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install flask python-dotenv requests websocket-client

# Check .env file
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Create .env with:"
    echo "DHAN_CLIENT_ID=your_client_id"
    echo "DHAN_ACCESS_TOKEN=your_access_token"
    echo "DHAN_TOTP=your_totp_secret"
    exit 1
fi

echo "✅ Dependencies installed!"
echo ""
echo "🚀 START COMMANDS:"
echo ""
echo "1. Start Flask API Server:"
echo "   python data_server_v2.py"
echo ""
echo "2. Start WebSocket Live Feed (new terminal):"
echo "   python websocket_client.py"
echo ""
echo "3. Test API:"
echo "   curl http://127.0.0.1:5000/health"
echo ""
echo "4. Fetch all indices all expiries:"
echo "   curl -X POST http://127.0.0.1:5000/data/fetch-all"
echo ""
echo "5. Get option chain (example):"
echo "   curl http://127.0.0.1:5000/data/option-chain/NIFTY/2026-05-29"
echo ""
echo "6. Get PCR data:"
echo "   curl http://127.0.0.1:5000/data/pcr/NIFTY/2026-05-29"
echo ""
echo "7. Get DB stats:"
echo "   curl http://127.0.0.1:5000/data/stats"
echo ""
echo "=========================================="
