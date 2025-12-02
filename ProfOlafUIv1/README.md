# Snowball Sampling Research Tool - Web UI

A modern web interface for the snowball sampling research paper collection tool. This application allows you to upload research paper titles and automatically collect metadata from Google Scholar using a beautiful, responsive web interface.

## Features

- **Modern Web Interface**: Clean, responsive design built with Bootstrap 5
- **File Upload**: Support for both `.txt` and `.json` file formats
- **Real-time Progress**: Live progress tracking with visual indicators
- **Database Viewer**: Browse collected data with search and filter capabilities
- **Results Display**: Detailed view of processing results with paper metadata
- **Background Processing**: Non-blocking paper processing with threading
- **Error Handling**: Graceful fallback to mock data when Google Scholar is unavailable

## Installation

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Setup

1. **Clone or download the project files**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the application**:
   - Ensure `search_conf.json` exists with proper configuration
   - Set up proxy configuration if needed (optional)
   - Create `.env` file for environment variables if required

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Access the web interface**:
   Open your browser and navigate to `http://localhost:5000`

## Usage

### 1. Upload Papers

1. Navigate to the home page
2. Click "Choose File" and select your input file:
   - **Text file (.txt)**: One paper title per line
   - **JSON file (.json)**: Format with `{"papers": [{"title": "Paper Title"}]}`
3. Adjust settings:
   - **Delay**: Time between Google Scholar requests (default: 2 seconds)
   - **Database Path**: Location of SQLite database file
4. Click "Start Processing"

### 2. Monitor Progress

- The progress page shows real-time updates
- View current processing step and completion percentage
- See total papers, processed count, and remaining items
- Processing runs in the background - you can navigate away and return

### 3. View Results

- After processing completes, view detailed results
- Search and filter papers by status
- Click "View Details" for complete paper information
- Export or download results as needed

### 4. Browse Database

- Access the database viewer to see all collected data
- View iterations table with all paper metadata
- Browse seen titles to avoid duplicates
- Use search and filter functions to find specific papers

## File Formats

### Text File Format
```
Paper Title 1
Paper Title 2
Paper Title 3
```

### JSON File Format
```json
{
  "papers": [
    {"title": "Paper Title 1"},
    {"title": "Paper Title 2"},
    {"title": "Paper Title 3"}
  ]
}
```

## Configuration

The application uses `search_conf.json` for configuration:

```json
{
    "start_year": 2020,
    "end_year": 2025,
    "venue_rank_list": ["A*", "A"],
    "proxy_key": "your-proxy-key",
    "initial_file": "seed.txt",
    "db_path": "database.db"
}
```

## API Endpoints

- `GET /` - Home page with upload form
- `POST /upload` - Handle file upload and start processing
- `GET /progress` - Progress monitoring page
- `GET /api/progress` - JSON API for progress updates
- `GET /results` - View processing results
- `GET /database` - Database viewer
- `GET /api/reset` - Reset progress data

## Database Schema

The application uses SQLite with the following tables:

### Iterations Table
- `id`: Unique paper identifier
- `title`: Paper title
- `authors`: Author names
- `venue`: Publication venue
- `pub_year`: Publication year
- `num_citations`: Citation count
- `iteration`: Iteration number
- `selected`: Selection status
- Additional metadata fields

### Seen Titles Table
- `title`: Normalized paper title
- `id`: Associated paper ID

## Troubleshooting

### Common Issues

1. **Google Scholar Rate Limiting**:
   - Increase the delay between requests
   - Use proxy configuration if available
   - The system will create mock data if Scholar is unavailable

2. **File Upload Errors**:
   - Ensure file format is supported (.txt or .json)
   - Check file size limits
   - Verify JSON format is valid

3. **Database Errors**:
   - Ensure database file is writable
   - Check file permissions
   - Verify SQLite installation

4. **Proxy Issues**:
   - Verify proxy configuration in `search_conf.json`
   - Test proxy connectivity
   - Application will continue without proxy if setup fails

### Error Messages

- **"No titles found"**: Check file format and content
- **"Unsupported file type"**: Use .txt or .json files only
- **"Database error"**: Check file permissions and path
- **"Proxy setup failed"**: Application continues without proxy

## Development

### Project Structure

```
ProfOlaf/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── search_conf.json      # Configuration file
├── templates/            # HTML templates
│   ├── index.html
│   ├── progress.html
│   ├── results.html
│   └── database.html
├── static/               # Static assets
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── progress.js
├── utils/                 # Utility modules
│   ├── db_management.py
│   └── proxy_generator.py
└── uploads/              # Upload directory
```

### Adding Features

1. **New Routes**: Add to `app.py`
2. **New Templates**: Create in `templates/`
3. **New Styles**: Add to `static/css/style.css`
4. **New Scripts**: Add to `static/js/`

## License

This project is part of the ProfOlaf research tool suite. Please refer to the main project documentation for licensing information.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review the configuration settings
3. Check the console output for error messages
4. Verify all dependencies are installed correctly
