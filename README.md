# New Permits - Texas RRC Mobile Web App

A mobile-friendly web application that automatically tracks and displays new oil & gas drilling permits from the Texas Railroad Commission (RRC).

## 🎯 Features

### Phase 1 - Core Features ✅
- **RRC Data Scraping**: Automatically pulls new drilling permits from the RRC public website
- **Database Storage**: Saves permit data in SQLite database
- **Comprehensive Fields**: County, Operator, Lease Name, Well Number, API Number, Date Issued, RRC Link
- **Mobile-Friendly UI**: Responsive design optimized for phones and tablets
- **Search & Filter**: Filter by county, search by operator/lease name
- **Sorting**: Show newest permits first or most recent additions
- **Export**: Download permit data as CSV

### Phase 2 - Advanced Features (Coming Soon)
- User login system with email/password
- County selection preferences
- Push notifications for new permits
- Advanced filtering options

## 🚀 Quick Start

### Local Development

1. **Clone or download the project files**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```

4. **Open your browser** and go to `http://localhost:5000`

### Cloud Deployment (Railway)

1. **Create a new Railway project**
2. **Connect your GitHub repository**
3. **Railway will automatically detect the Python app and deploy it**

## 📱 How to Use

### 1. View Permits
- The homepage shows all permits in a mobile-friendly card layout
- Each card displays: County, Operator, Lease, Well Number, API, Date
- Click "🌐 View on RRC" to open the original permit on the RRC website

### 2. Search & Filter
- **County Filter**: Select a specific county from the dropdown
- **Search**: Type operator or lease name to find specific permits
- **Sort**: Choose "Newest Permits First" to see permits by issue date

### 3. Scrape New Permits
- Click "🔄 Scrape New Permits" to fetch the latest permits from RRC
- The app will show "Scraping..." status and refresh automatically
- New permits are added to the database and displayed

### 4. Export Data
- Click "📊 Export CSV" to download all permits as a spreadsheet
- Perfect for analysis in Excel or Google Sheets

## 🛠️ Technical Details

### Tech Stack
- **Backend**: Python Flask
- **Database**: SQLite (local) / PostgreSQL (production)
- **Frontend**: HTML5, CSS3, JavaScript
- **Scraping**: Requests + BeautifulSoup
- **Deployment**: Railway, Render, or similar

### Database Schema
```sql
CREATE TABLE permit (
    id INTEGER PRIMARY KEY,
    county VARCHAR(100) NOT NULL,
    operator VARCHAR(200) NOT NULL,
    lease_name VARCHAR(200) NOT NULL,
    well_number VARCHAR(100) NOT NULL,
    api_number VARCHAR(50),
    date_issued DATE NOT NULL,
    rrc_link VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### API Endpoints
- `GET /` - Main application page
- `POST /api/scrape` - Start scraping for new permits
- `GET /api/status` - Get scraping status
- `GET /api/permits` - Get permits as JSON
- `GET /export/csv` - Export permits as CSV

## 🔧 Configuration

### Environment Variables
- `DATABASE_URL` - Database connection string (auto-set by Railway)
- `SECRET_KEY` - Flask secret key (auto-generated)
- `PORT` - Server port (auto-set by Railway)

### Customization
- **Counties**: Edit `TEXAS_COUNTIES` list in `app.py` to add/remove counties
- **Scraping**: Modify `scrape_rrc_permits()` function for different data sources
- **UI**: Customize CSS in `templates/index.html` for different styling

## 📊 Sample Data

The app includes sample permits for testing:
- **Harris County**: Exxon Mobil Corporation - Baytown Refinery Unit
- **Travis County**: Chevron U.S.A. Inc. - Austin Chalk Unit  
- **Midland County**: Pioneer Natural Resources - Permian Basin Unit

## 🚨 Troubleshooting

### Common Issues

1. **"No permits found"**
   - Click "🔄 Scrape New Permits" to fetch data
   - Check your internet connection
   - Verify RRC website is accessible

2. **Scraping fails**
   - RRC website may be temporarily down
   - Check the status section for error messages
   - Try again in a few minutes

3. **Mobile display issues**
   - Ensure you're using a modern browser
   - Try refreshing the page
   - Check if JavaScript is enabled

### Development Issues

1. **Database errors**
   - Delete `permits.db` file and restart the app
   - Check database permissions

2. **Import errors**
   - Run `pip install -r requirements.txt`
   - Ensure you're using Python 3.7+

## 🔮 Future Enhancements

- **Real-time notifications** when new permits are found
- **User accounts** to save preferences and search history
- **Advanced analytics** with charts and graphs
- **Email alerts** for specific counties or operators
- **Mobile app** (React Native or Flutter)
- **API access** for third-party integrations

## 📄 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

---

**Built with ❤️ for the Texas oil & gas industry**