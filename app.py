"""
URL Shortener - Ana Flask Uygulaması
Bu dosya web uygulamasının ana giriş noktasıdır.

Tüm route'lar, error handling, ve middleware'ler burada tanımlanır.
Production-ready güvenlik ve performans optimizasyonları içerir.
"""

import os
import logging
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, URL
from werkzeug.exceptions import NotFound, BadRequest, TooManyRequests
from flask_wtf.csrf import CSRFError

# Local imports
from config import get_config, validate_config
from models import db, Url, User, init_db
from utils import (
    create_short_url, url_validator, format_click_count,
    get_domain_from_url, stats_helper
)


def create_app(config_name=None):
    """
    Flask application factory pattern
    
    Bu pattern sayesinde farklı konfigürasyonlarla (test, dev, prod)
    ayrı app instance'ları oluşturabiliriz.
    
    Args:
        config_name (str, optional): Konfigürasyon adı
        
    Returns:
        Flask: Konfigüre edilmiş Flask app instance'ı
    """
    app = Flask(__name__)
    
    # Konfigürasyon yükleme
    config_class = get_config()
    app.config.from_object(config_class)
    
    # Konfigürasyon validation
    warnings = validate_config(app)
    for warning in warnings:
        app.logger.warning(warning)
    
    # Extensions initialize
    db.init_app(app)
    csrf = CSRFProtect(app)
    
    # Database initialization
    with app.app_context():
        db.create_all()
        
        # Development ortamında sample data oluştur
        if app.debug and os.environ.get('CREATE_SAMPLE_DATA', 'false').lower() == 'true':
            from models import create_sample_data
            create_sample_data()
    
    # Error handler'ları register et
    register_error_handlers(app)
    
    # Template filter'ları register et
    register_template_filters(app)
    
    # Request handler'ları register et
    register_request_handlers(app)
    
    return app


def register_blueprints(app):
    """
    Blueprint'leri register eder - şimdilik devre dışı
    
    Routes doğrudan app'te tanımlanıyor.
    Gelecekte modüler yapı için blueprint'ler kullanılabilir.
    """
    pass  # Şimdilik blueprint kullanmıyoruz


def register_error_handlers(app):
    """
    Global error handler'ları register eder
    
    Kullanıcı dostu error sayfaları ve güvenli error handling sağlar.
    """
    
    @app.errorhandler(404)
    def not_found_error(error):
        """404 - Sayfa bulunamadı"""
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(400)
    def bad_request_error(error):
        """400 - Geçersiz istek"""
        return render_template('errors/400.html'), 400
    
    @app.errorhandler(429)
    def rate_limit_error(error):
        """429 - Rate limit aşıldı"""
        return render_template('errors/429.html'), 429
    
    @app.errorhandler(500)
    def internal_error(error):
        """500 - Sunucu hatası"""
        db.session.rollback()  # Database transaction'ı geri al
        app.logger.error(f'Server Error: {error}')
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(CSRFError)
    def csrf_error(error):
        """CSRF token hatası"""
        flash('Güvenlik doğrulaması başarısız. Lütfen sayfayı yenileyin.', 'error')
        return redirect(url_for('main.index'))


def register_template_filters(app):
    """
    Jinja2 template filter'larını register eder
    """
    
    @app.template_filter('format_count')
    def format_count_filter(count):
        """Sayıları kullanıcı dostu formatta gösterir"""
        return format_click_count(count)
    
    @app.template_filter('domain_from_url')
    def domain_from_url_filter(url):
        """URL'den domain çıkarır"""
        return get_domain_from_url(url)
    
    @app.template_filter('time_ago')
    def time_ago_filter(dt):
        """Zamanı 'x dakika önce' formatında gösterir"""
        if not dt:
            return "Bilinmiyor"
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        # dt'yi timezone-aware yap
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days} gün önce"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} saat önce"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} dakika önce"
        else:
            return "Az önce"


def register_request_handlers(app):
    """
    Request lifecycle handler'larını register eder
    """
    
    @app.before_request
    def before_request():
        """Her request'ten önce çalışır"""
        # Rate limiting (gelecekte implement edilebilir)
        pass
    
    @app.after_request
    def after_request(response):
        """Her request'ten sonra çalışır"""
        # Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # HTTPS redirect header (production için)
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response


# WTForms formları
class URLShortenForm(FlaskForm):
    """
    URL kısaltma formu
    
    Kullanıcıdan URL ve opsiyonel custom kod alır.
    Client-side ve server-side validation içerir.
    """
    url = StringField(
        'URL',
        validators=[
            DataRequired(message='URL alanı zorunludur'),
            Length(min=10, max=2048, message='URL 10-2048 karakter arasında olmalıdır'),
            URL(message='Geçerli bir URL giriniz')
        ],
        render_kw={
            'placeholder': 'https://example.com/very/long/url',
            'class': 'form-control',
            'autocomplete': 'url'
        }
    )
    
    custom_code = StringField(
        'Özel Kod (İsteğe Bağlı)',
        validators=[
            Optional(),
            Length(min=3, max=20, message='Özel kod 3-20 karakter arasında olmalıdır')
        ],
        render_kw={
            'placeholder': 'my-custom-code',
            'class': 'form-control',
            'pattern': '[a-zA-Z0-9_-]+',
            'title': 'Sadece harf, rakam, tire (-) ve alt çizgi (_) kullanabilirsiniz'
        }
    )
    
    description = TextAreaField(
        'Açıklama (İsteğe Bağlı)',
        validators=[
            Optional(),
            Length(max=200, message='Açıklama en fazla 200 karakter olabilir')
        ],
        render_kw={
            'placeholder': 'Bu URL hakkında kısa bir açıklama...',
            'class': 'form-control',
            'rows': 3
        }
    )
    
    submit = SubmitField(
        'Kısalt!',
        render_kw={'class': 'btn btn-primary btn-lg'}
    )


# Routes (Blueprint'e taşınabilir)
class Routes:
    """
    Route tanımları için sınıf
    
    Bu pattern sayesinde route'lar organize edilir ve test edilebilir hale gelir.
    """
    
    def __init__(self, app):
        self.app = app
        self.register_routes()
    
    def register_routes(self):
        """Tüm route'ları register eder"""
        
        @self.app.route('/', methods=['GET', 'POST'])
        def index():
            """
            Ana sayfa - URL kısaltma formu
            
            GET: Formu gösterir
            POST: URL kısaltma işlemini yapar
            """
            form = URLShortenForm()
            
            if form.validate_on_submit():
                original_url = form.url.data.strip()
                custom_code = form.custom_code.data.strip() if form.custom_code.data else None
                description = form.description.data.strip() if form.description.data else None
                
                # Mevcut kodları al (çakışma kontrolü için)
                existing_codes = {url.short_code for url in Url.query.all()}
                
                # URL kısaltma işlemi
                success, short_code, error_msg = create_short_url(
                    original_url, custom_code, existing_codes
                )
                
                if success:
                    # Veritabanına kaydet
                    try:
                        url_obj = Url(
                            original_url=original_url,
                            short_code=short_code,
                            description=description
                        )
                        db.session.add(url_obj)
                        db.session.commit()
                        
                        # Başarı mesajı
                        flash('URL başarıyla kısaltıldı!', 'success')
                        
                        # Result sayfasına yönlendir
                        return redirect(url_for('result', code=short_code))
                    
                    except Exception as e:
                        db.session.rollback()
                        self.app.logger.error(f'Database error: {e}')
                        flash('Bir hata oluştu. Lütfen tekrar deneyin.', 'error')
                else:
                    flash(error_msg, 'error')
            
            # Son oluşturulan URL'leri göster (isteğe bağlı)
            recent_urls = Url.query.filter_by(is_active=True)\
                             .order_by(Url.created_at.desc())\
                             .limit(5).all()
            
            return render_template('index.html', form=form, recent_urls=recent_urls)
        
        @self.app.route('/r/<string:code>')
        @self.app.route('/<string:code>')  # Kısa URL için
        def redirect_url(code):
            """
            Kısa URL yönlendirme
            
            Kısa koda göre orijinal URL'yi bulur ve yönlendirir.
            Tıklama sayısını artırır.
            """
            # URL'yi bul
            url_obj = Url.find_by_short_code(code)
            
            if not url_obj:
                # 404 sayfası göster
                abort(404)
            
            # Tıklama sayısını artır (async olarak yapılabilir)
            try:
                url_obj.increment_click_count()
            except Exception as e:
                self.app.logger.warning(f'Click count update failed: {e}')
                # Hata olsa bile yönlendirmeyi devam ettir
            
            # Orijinal URL'ye yönlendir
            return redirect(url_obj.original_url)
        
        @self.app.route('/result/<string:code>')
        def result(code):
            """
            URL kısaltma sonuç sayfası
            
            Oluşturulan kısa URL'yi ve detayları gösterir.
            """
            url_obj = Url.find_by_short_code(code)
            
            if not url_obj:
                flash('Kısa URL bulunamadı.', 'error')
                return redirect(url_for('index'))
            
            # Full URL oluştur
            short_url = request.url_root.rstrip('/') + '/' + code
            
            return render_template('result.html', url_obj=url_obj, short_url=short_url)
        
        @self.app.route('/stats/<string:code>')
        def stats(code):
            """
            URL istatistikleri sayfası
            
            Belirli bir kısa URL'nin detaylı istatistiklerini gösterir.
            """
            url_obj = Url.find_by_short_code(code)
            
            if not url_obj:
                abort(404)
            
            return render_template('stats.html', url_obj=url_obj)
        
        @self.app.route('/api/shorten', methods=['POST'])
        def api_shorten():
            """
            API endpoint - URL kısaltma
            
            JSON formatında URL kısaltma servisi sağlar.
            Rate limiting ve authentication eklenebilir.
            """
            try:
                data = request.get_json()
                
                if not data or 'url' not in data:
                    return jsonify({'error': 'URL gereklidir'}), 400
                
                original_url = data['url'].strip()
                custom_code = data.get('custom_code', '').strip() or None
                
                # Validation
                is_valid, error_msg = url_validator.is_valid_url(original_url)
                if not is_valid:
                    return jsonify({'error': error_msg}), 400
                
                # Mevcut kodları al
                existing_codes = {url.short_code for url in Url.query.all()}
                
                # URL kısalt
                success, short_code, error_msg = create_short_url(
                    original_url, custom_code, existing_codes
                )
                
                if not success:
                    return jsonify({'error': error_msg}), 400
                
                # Veritabanına kaydet
                url_obj = Url(
                    original_url=original_url,
                    short_code=short_code,
                    description=data.get('description')
                )
                db.session.add(url_obj)
                db.session.commit()
                
                # Response
                short_url = request.url_root.rstrip('/') + '/' + short_code
                
                return jsonify({
                    'success': True,
                    'short_code': short_code,
                    'short_url': short_url,
                    'original_url': original_url,
                    'stats_url': url_for('stats', code=short_code, _external=True)
                }), 201
            
            except Exception as e:
                db.session.rollback()
                self.app.logger.error(f'API Error: {e}')
                return jsonify({'error': 'Sunucu hatası'}), 500
        
        @self.app.route('/api/stats/<string:code>')
        def api_stats(code):
            """
            API endpoint - URL istatistikleri
            
            JSON formatında URL istatistiklerini döner.
            """
            url_obj = Url.find_by_short_code(code)
            
            if not url_obj:
                return jsonify({'error': 'URL bulunamadı'}), 404
            
            return jsonify(url_obj.to_dict())
        
        @self.app.route('/dashboard')
        def dashboard():
            """
            Dashboard sayfası - Genel istatistikler
            
            Toplam URL sayısı, tıklama sayısı vb. istatistikleri gösterir.
            """
            # Toplam istatistikler
            total_urls = Url.query.filter_by(is_active=True).count()
            total_clicks = db.session.query(db.func.sum(Url.click_count)).scalar() or 0
            
            # En çok tıklanan URL'ler
            popular_urls = Url.query.filter_by(is_active=True)\
                              .order_by(Url.click_count.desc())\
                              .limit(10).all()
            
            # Son oluşturulan URL'ler
            recent_urls = Url.query.filter_by(is_active=True)\
                             .order_by(Url.created_at.desc())\
                             .limit(10).all()
            
            return render_template('dashboard.html', 
                                 total_urls=total_urls,
                                 total_clicks=total_clicks,
                                 popular_urls=popular_urls,
                                 recent_urls=recent_urls)


# Flask app oluştur
app = create_app()

# Route'ları register et
routes = Routes(app)

# CLI commands (flask komutları)
@app.cli.command()
def init_db_command():
    """Database'i initialize eder"""
    init_db(app)
    print('✅ Database initialized!')

@app.cli.command()
def create_sample_data_command():
    """Sample data oluşturur"""
    from models import create_sample_data
    create_sample_data()
    print('✅ Sample data created!')


if __name__ == '__main__':
    # Development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True  # Multi-threading support
    )