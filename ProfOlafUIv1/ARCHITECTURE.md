# ProfOlaf - Snowball Sampling Research Tool Architecture

## Overview
ProfOlaf is a comprehensive web-based tool for conducting snowball sampling research on academic papers. It provides a modern, user-friendly interface for collecting, processing, and analyzing research paper metadata from Google Scholar.

## Frontend Architecture

### UI Framework
- **Bootstrap 5.1.3**: Modern responsive UI framework with custom styling
- **Font Awesome 6.0.0**: Comprehensive icon library for enhanced UX
- **Custom CSS**: Gradient designs, animations, and responsive layouts
- **JavaScript**: Real-time progress monitoring and interactive features

### Design System
- **Lateral Navigation**: Consistent sidebar menu across all pages
- **Card-based Layout**: Clean, organized content presentation
- **Gradient Themes**: Professional color schemes (blue-purple gradients)
- **Responsive Design**: Mobile-first approach with breakpoints

## Backend Architecture

### Core Framework
- **Flask 2.3.3**: Lightweight web framework with Jinja2 templating
- **Werkzeug 2.3.7**: WSGI utilities and development server
- **Threading**: Background processing for non-blocking operations
- **SQLite**: Embedded database for data persistence

### External Integrations
- **Google Scholar API**: Paper metadata collection via scholarly library
- **Proxy Support**: Optional proxy configuration for rate limiting
- **File Processing**: Support for .txt and .json input formats

## Application Structure

### Page Architecture
1. **Dashboard** (`/`): Main landing page with feature overview
2. **Upload Papers** (`/upload`): File upload and configuration interface
3. **Snowball Start** (`/snowball-start`): One-time initialization process
4. **Database Viewer** (`/database`): Database content browsing and search
5. **Progress Monitor** (`/progress`): Real-time processing status
6. **Results Display** (`/results`): Detailed processing results

### API Endpoints
- **`/api/progress`**: Real-time progress data (JSON)
- **`/api/generate_search_conf`**: Configuration generation
- **`/api/reset`**: Progress data reset functionality
- **`/upload_file`**: File upload processing
- **`/run-snowball-start`**: Snowball initialization execution

## Data Flow Architecture

### Snowball Initialization Process
1. **File Upload** → User uploads .txt/.json file with paper titles
2. **Configuration** → User sets parameters (years, ranks, proxy, etc.)
3. **Background Processing** → Thread processes each paper title
4. **Google Scholar Search** → API calls with rate limiting
5. **Data Extraction** → Metadata collection (authors, venue, citations)
6. **Database Storage** → SQLite insertion with progress tracking
7. **Real-time Updates** → AJAX polling for progress monitoring

### Configuration Management
- **search_conf.json**: Persistent configuration storage
- **Dynamic Updates**: Real-time configuration modification
- **Parameter Validation**: Input validation and error handling

## Database Schema

### Core Tables
- **iterations**: Main paper data (title, authors, venue, citations, etc.)
- **seen_titles**: Tracked paper titles to prevent duplicates
- **conf_rank**: Venue ranking configuration

### Data Models
- **ArticleData**: Structured paper metadata
- **SelectionStage**: Enum for paper selection status
- **DBManager**: Database operations and management

## Key Features

### User Experience
- **One-time Setup**: Clear separation of initialization vs. regular processing
- **Real-time Monitoring**: Live progress updates with visual indicators
- **Error Handling**: Graceful fallbacks and user-friendly error messages
- **File Preview**: Pre-processing file validation and preview

### Technical Features
- **Non-blocking Processing**: Background threading prevents UI freezing
- **Rate Limiting**: Configurable delays to respect API limits
- **Proxy Support**: Optional proxy configuration for enhanced access
- **Search & Filter**: Database browsing with real-time search
- **Responsive Design**: Cross-device compatibility

### Security & Performance
- **Input Validation**: File type and content validation
- **Error Recovery**: Robust error handling and recovery mechanisms
- **Memory Management**: Efficient data processing and storage
- **Scalability**: Thread-based architecture supports concurrent operations

## Development Workflow

### File Organization
```
ProfOlaf/
├── templates/          # Jinja2 HTML templates
├── static/            # CSS, JS, and assets
├── utils/             # Database and proxy utilities
├── uploads/           # Temporary file storage
├── app.py            # Main Flask application
├── search_conf.json  # Configuration file
└── database.db       # SQLite database
```

### Configuration Management
- **Environment Variables**: .env file support via python-dotenv
- **JSON Configuration**: search_conf.json for persistent settings
- **Runtime Parameters**: Dynamic configuration updates

## Deployment Considerations

### Requirements
- **Python 3.12+**: Modern Python with type hints support
- **Dependencies**: Flask, scholarly, requests, tqdm, python-dotenv
- **Storage**: SQLite database and file uploads directory
- **Network**: Internet access for Google Scholar API

### Production Readiness
- **Development Server**: Werkzeug development server (not production-ready)
- **WSGI Deployment**: Ready for Gunicorn/uWSGI deployment
- **Database**: SQLite suitable for development, consider PostgreSQL for production
- **Static Files**: CDN-ready static asset structure

## Future Enhancements

### Planned Features
- **Batch Processing**: Multiple file processing capabilities
- **Export Options**: CSV, JSON, and other format exports
- **Advanced Filtering**: Complex database query capabilities
- **User Management**: Multi-user support and authentication
- **API Documentation**: Comprehensive API documentation

### Scalability Improvements
- **Database Migration**: PostgreSQL support for larger datasets
- **Caching Layer**: Redis integration for improved performance
- **Microservices**: Service separation for better scalability
- **Containerization**: Docker support for easy deployment