"""
URL Shortener - Veritabanı Modelleri
SQLAlchemy ORM kullanarak veritabanı tablolarını tanımlar.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# SQLAlchemy instance'ı - app.py'da initialize edilecek
db = SQLAlchemy()


class Url(db.Model):
    """
    URL tablosu - Kısaltılan URL'leri saklar
    
    Bu tablo orijinal URL ile kısa kod arasındaki eşleştirmeyi tutar.
    Ayrıca tıklama sayısını ve oluşturulma zamanını da saklar.
    """
    __tablename__ = 'urls'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Orijinal uzun URL - zorunlu alan
    original_url = db.Column(db.Text, nullable=False)
    
    # Kısa kod (benzersiz) - bit.ly'deki gibi random string
    short_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    
    # Oluşturulma zamanı - otomatik set edilir
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Tıklama sayısı - varsayılan 0
    click_count = db.Column(db.Integer, nullable=False, default=0)
    
    # İsteğe bağlı: Kullanıcı ilişkisi (anonim URL'ler için None olabilir)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # İsteğe bağlı: Son erişim zamanı
    last_accessed = db.Column(db.DateTime, nullable=True)
    
    # İsteğe bağlı: Açıklama
    description = db.Column(db.String(200), nullable=True)
    
    # İsteğe bağlı: Aktif/pasif durumu
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    
    def __init__(self, original_url, short_code, user_id=None, description=None):
        """
        Url model constructor
        
        Args:
            original_url (str): Orijinal uzun URL
            short_code (str): Benzersiz kısa kod
            user_id (int, optional): Kullanıcı ID'si
            description (str, optional): URL açıklaması
        """
        self.original_url = original_url
        self.short_code = short_code
        self.user_id = user_id
        self.description = description
    
    def increment_click_count(self):
        """
        Tıklama sayısını artırır ve son erişim zamanını günceller.
        
        Bu method thread-safe olarak tasarlanmıştır.
        """
        self.click_count += 1
        self.last_accessed = datetime.utcnow()
        db.session.commit()
    
    def to_dict(self):
        """
        Model'i dictionary formatına çevirir (API için)
        
        Returns:
            dict: URL bilgilerini içeren sözlük
        """
        return {
            'id': self.id,
            'original_url': self.original_url,
            'short_code': self.short_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'click_count': self.click_count,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
            'description': self.description,
            'is_active': self.is_active
        }
    
    def __repr__(self):
        """String representation"""
        return f'<Url {self.short_code}: {self.original_url[:50]}...>'
    
    @staticmethod
    def find_by_short_code(short_code):
        """
        Kısa koda göre URL bulur
        
        Args:
            short_code (str): Aranacak kısa kod
            
        Returns:
            Url: Bulunan URL objesi veya None
        """
        return Url.query.filter_by(short_code=short_code, is_active=True).first()
    
    @staticmethod
    def is_short_code_available(short_code):
        """
        Kısa kodun mevcut olup olmadığını kontrol eder
        
        Args:
            short_code (str): Kontrol edilecek kısa kod
            
        Returns:
            bool: True eğer kod müsaitse
        """
        return Url.query.filter_by(short_code=short_code).first() is None


class User(db.Model):
    """
    Kullanıcı tablosu - İsteğe bağlı kullanıcı yönetimi için
    
    Bu tablo kullanıcıların kendi URL'lerini takip etmelerini sağlar.
    Temel authentication ve URL ownership için kullanılır.
    """
    __tablename__ = 'users'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Kullanıcı adı - benzersiz ve zorunlu
    username = db.Column(db.String(80), unique=True, nullable=False)
    
    # Email - benzersiz ve zorunlu
    email = db.Column(db.String(120), unique=True, nullable=False)
    
    # Hash'lenmiş şifre - düz şifre saklanmaz!
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Oluşturulma zamanı
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Aktif/pasif durumu
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    
    # One-to-many ilişki: Bir kullanıcının birden fazla URL'si olabilir
    urls = db.relationship('Url', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, username, email, password):
        """
        User model constructor
        
        Args:
            username (str): Kullanıcı adı
            email (str): Email adresi
            password (str): Düz şifre (hash'lenecek)
        """
        self.username = username
        self.email = email
        self.set_password(password)
    
    def set_password(self, password):
        """
        Şifreyi güvenli bir şekilde hash'ler ve saklar
        
        Args:
            password (str): Düz şifre
        """
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """
        Girilen şifreyi hash ile karşılaştırır
        
        Args:
            password (str): Kontrol edilecek şifre
            
        Returns:
            bool: Şifre doğruysa True
        """
        return check_password_hash(self.password_hash, password)
    
    def get_url_count(self):
        """
        Kullanıcının toplam URL sayısını döner
        
        Returns:
            int: Aktif URL sayısı
        """
        return Url.query.filter_by(user_id=self.id, is_active=True).count()
    
    def get_total_clicks(self):
        """
        Kullanıcının tüm URL'lerinin toplam tıklama sayısı
        
        Returns:
            int: Toplam tıklama sayısı
        """
        total = db.session.query(db.func.sum(Url.click_count))\
                         .filter_by(user_id=self.id, is_active=True)\
                         .scalar()
        return total or 0
    
    def to_dict(self):
        """
        Model'i dictionary formatına çevirir (şifre hariç)
        
        Returns:
            dict: Kullanıcı bilgilerini içeren sözlük
        """
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self.is_active,
            'url_count': self.get_url_count(),
            'total_clicks': self.get_total_clicks()
        }
    
    def __repr__(self):
        """String representation"""
        return f'<User {self.username}>'
    
    @staticmethod
    def find_by_username(username):
        """
        Kullanıcı adına göre kullanıcı bulur
        
        Args:
            username (str): Aranacak kullanıcı adı
            
        Returns:
            User: Bulunan kullanıcı objesi veya None
        """
        return User.query.filter_by(username=username, is_active=True).first()
    
    @staticmethod
    def find_by_email(email):
        """
        Email'e göre kullanıcı bulur
        
        Args:
            email (str): Aranacak email
            
        Returns:
            User: Bulunan kullanıcı objesi veya None
        """
        return User.query.filter_by(email=email, is_active=True).first()


def init_db(app):
    """
    Veritabanını initialize eder ve tabloları oluşturur
    
    Bu fonksiyon app.py'da çağrılacak.
    
    Args:
        app: Flask application instance
    """
    db.init_app(app)
    
    with app.app_context():
        # Tüm tabloları oluştur
        db.create_all()
        
        print("✅ Veritabanı tabloları başarıyla oluşturuldu!")


def create_sample_data():
    """
    Test için örnek veri oluşturur (sadece geliştirme ortamında kullanın!)
    
    Bu fonksiyonu production ortamında ÇALIŞMAYACAK şekilde koruma altına alın.
    """
    # Örnek kullanıcı oluştur
    if not User.find_by_username('demo'):
        demo_user = User(
            username='demo',
            email='demo@example.com',
            password='demo123'  # Production'da daha güvenli şifre kullanın!
        )
        db.session.add(demo_user)
        db.session.commit()
        
        # Örnek URL'ler oluştur
        sample_urls = [
            {
                'original_url': 'https://www.google.com',
                'short_code': 'google',
                'description': 'Google Ana Sayfası'
            },
            {
                'original_url': 'https://github.com',
                'short_code': 'github',
                'description': 'GitHub'
            },
            {
                'original_url': 'https://stackoverflow.com',
                'short_code': 'stack',
                'description': 'Stack Overflow'
            }
        ]
        
        for url_data in sample_urls:
            if Url.is_short_code_available(url_data['short_code']):
                url = Url(
                    original_url=url_data['original_url'],
                    short_code=url_data['short_code'],
                    user_id=demo_user.id,
                    description=url_data['description']
                )
                db.session.add(url)
        
        db.session.commit()
        print("✅ Örnek veriler oluşturuldu!")