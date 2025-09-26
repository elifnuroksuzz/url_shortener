"""
URL Shortener - Yardımcı Fonksiyonlar
URL kısaltma, doğrulama ve çeşitli utility fonksiyonları.

Bu modül uygulamanın core business logic'ini içerir.
Tüm fonksiyonlar pure function olarak tasarlanmıştır (side effect yok).
"""

import re
import random
import string
import hashlib
import validators
from urllib.parse import urlparse, urlunparse
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict


class URLShortener:
    """
    URL kısaltma işlemleri için ana sınıf
    
    Bu sınıf farklı algoritmaları destekler:
    - Random string generation
    - Hash-based generation
    - Custom user-defined codes
    """
    
    def __init__(self, alphabet: str = None, length: int = 6):
        """
        URLShortener constructor
        
        Args:
            alphabet (str): Kısa kod için kullanılacak karakterler
            length (int): Varsayılan kısa kod uzunluğu
        """
        self.alphabet = alphabet or 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        self.length = length
        
        # Karışık karakterleri önlemek için bazı karakterleri çıkar
        self.safe_alphabet = self.alphabet.translate(str.maketrans('', '', '0O1lI'))
    
    def generate_random_code(self, length: Optional[int] = None) -> str:
        """
        Rastgele kısa kod üretir
        
        Args:
            length (int, optional): Kod uzunluğu (varsayılan self.length)
            
        Returns:
            str: Rastgele kısa kod
        """
        code_length = length or self.length
        return ''.join(random.choices(self.safe_alphabet, k=code_length))
    
    def generate_hash_based_code(self, url: str, length: Optional[int] = None) -> str:
        """
        URL'nin hash'ine dayalı deterministik kod üretir
        
        Aynı URL için her zaman aynı kodu üretir (caching için yararlı).
        
        Args:
            url (str): Hash'lenecek URL
            length (int, optional): Kod uzunluğu
            
        Returns:
            str: Hash tabanlı kısa kod
        """
        code_length = length or self.length
        
        # URL'yi normalize et
        normalized_url = URLValidator.normalize_url(url)
        
        # SHA-256 hash'i al
        hash_object = hashlib.sha256(normalized_url.encode())
        hash_hex = hash_object.hexdigest()
        
        # Hash'i alphabet'e dönüştür
        code = ''
        for i in range(code_length):
            # Hash'in her 2 karakterini alphabet index'ine çevir
            hex_pair = hash_hex[i*2:(i*2)+2]
            index = int(hex_pair, 16) % len(self.safe_alphabet)
            code += self.safe_alphabet[index]
        
        return code
    
    def generate_unique_code(self, url: str, existing_codes: set, 
                           max_attempts: int = 100) -> Optional[str]:
        """
        Benzersiz kısa kod üretir (mevcut kodlarla çakışmayan)
        
        Args:
            url (str): Kısaltılacak URL
            existing_codes (set): Mevcut kodlar listesi
            max_attempts (int): Maksimum deneme sayısı
            
        Returns:
            str: Benzersiz kod veya None (başarısızlık durumunda)
        """
        # Önce hash-based dene
        hash_code = self.generate_hash_based_code(url)
        if hash_code not in existing_codes:
            return hash_code
        
        # Hash çakışırsa random deneme yap
        for attempt in range(max_attempts):
            # Uzunluğu artırarak dene
            length = self.length + (attempt // 10)  # Her 10 denemede uzunluk +1
            random_code = self.generate_random_code(length)
            
            if random_code not in existing_codes:
                return random_code
        
        return None  # Benzersiz kod üretilemedi


class URLValidator:
    """
    URL doğrulama ve normalizasyon işlemleri
    """
    
    # Güvenli protokoller
    ALLOWED_SCHEMES = {'http', 'https', 'ftp', 'ftps'}
    
    # Yasaklı domain'ler (kendi domain'imizi kısaltmayı engellemek için)
    BLOCKED_DOMAINS = {
        'localhost',
        '127.0.0.1',
        '0.0.0.0'
    }
    
    # Şüpheli TLD'ler
    SUSPICIOUS_TLDS = {
        'tk', 'ml', 'ga', 'cf',  # Ücretsiz domain'ler
        'bit', 'ly'  # Diğer URL shortener'lar
    }
    
    @staticmethod
    def is_valid_url(url: str, strict: bool = True) -> Tuple[bool, str]:
        """
        URL'nin geçerli olup olmadığını kontrol eder
        
        Args:
            url (str): Kontrol edilecek URL
            strict (bool): Katı doğrulama modu
            
        Returns:
            Tuple[bool, str]: (geçerli_mi, hata_mesajı)
        """
        if not url or not isinstance(url, str):
            return False, "URL boş olamaz"
        
        # Uzunluk kontrolü
        if len(url) > 2048:
            return False, "URL çok uzun (max 2048 karakter)"
        
        if len(url) < 10:
            return False, "URL çok kısa"
        
        # Temel format kontrolü
        if not validators.url(url):
            return False, "Geçersiz URL formatı"
        
        try:
            parsed = urlparse(url)
        except Exception:
            return False, "URL parse edilemedi"
        
        # Protokol kontrolü
        if parsed.scheme.lower() not in URLValidator.ALLOWED_SCHEMES:
            return False, f"Desteklenmeyen protokol: {parsed.scheme}"
        
        # Domain kontrolü
        if not parsed.netloc:
            return False, "Domain belirtilmemiş"
        
        domain = parsed.netloc.lower().split(':')[0]  # Port'u çıkar
        
        # Yasaklı domain kontrolü
        if domain in URLValidator.BLOCKED_DOMAINS:
            return False, f"Yasaklı domain: {domain}"
        
        # Strict modda ek kontroller
        if strict:
            # TLD kontrolü
            domain_parts = domain.split('.')
            if len(domain_parts) >= 2:
                tld = domain_parts[-1]
                if tld in URLValidator.SUSPICIOUS_TLDS:
                    return False, f"Şüpheli TLD: {tld}"
            
            # Local IP adresi kontrolü
            if URLValidator._is_local_ip(domain):
                return False, "Yerel IP adresleri desteklenmiyor"
        
        return True, ""
    
    @staticmethod
    def _is_local_ip(domain: str) -> bool:
        """
        Domain'in yerel IP adresi olup olmadığını kontrol eder
        
        Args:
            domain (str): Kontrol edilecek domain
            
        Returns:
            bool: Yerel IP ise True
        """
        # IPv4 regex pattern
        ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        
        if re.match(ipv4_pattern, domain):
            parts = domain.split('.')
            
            # RFC 1918 private IP ranges
            if parts[0] == '10':  # 10.0.0.0/8
                return True
            if parts[0] == '172' and 16 <= int(parts[1]) <= 31:  # 172.16.0.0/12
                return True
            if parts[0] == '192' and parts[1] == '168':  # 192.168.0.0/16
                return True
            
            # Loopback
            if parts[0] == '127':  # 127.0.0.0/8
                return True
        
        return False
    
    @staticmethod  
    def normalize_url(url: str) -> str:
        """
        URL'yi normalize eder (tutarlılık için)
        
        Args:
            url (str): Normalize edilecek URL
            
        Returns:
            str: Normalize edilmiş URL
        """
        if not url:
            return url
        
        # Başındaki ve sonundaki boşlukları temizle
        url = url.strip()
        
        # Protokol yoksa http ekle
        if not url.startswith(('http://', 'https://', 'ftp://', 'ftps://')):
            url = 'http://' + url
        
        try:
            parsed = urlparse(url)
            
            # Domain'i küçük harfe çevir
            netloc = parsed.netloc.lower()
            
            # Varsayılan port'ları kaldır
            if netloc.endswith(':80') and parsed.scheme == 'http':
                netloc = netloc[:-3]
            elif netloc.endswith(':443') and parsed.scheme == 'https':
                netloc = netloc[:-4]
            
            # URL'yi yeniden oluştur
            normalized = urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
            
            return normalized
            
        except Exception:
            return url  # Parse edilemezse orijinal URL'yi döndür


class CodeValidator:
    """
    Kısa kod doğrulama işlemleri
    """
    
    # Yasaklı kelimeler (SEO ve güvenlik için)
    RESERVED_WORDS = {
        'api', 'admin', 'www', 'mail', 'ftp', 'blog', 'shop',
        'login', 'register', 'signup', 'signin', 'logout',
        'dashboard', 'profile', 'settings', 'config',
        'about', 'contact', 'help', 'support', 'terms', 'privacy',
        'index', 'home', 'main', 'root', 'null', 'undefined',
        'test', 'demo', 'sample', 'example',
        'css', 'js', 'img', 'images', 'static', 'assets',
        'fuck', 'shit', 'damn', 'porn', 'sex'  # Küfür filtresi
    }
    
    @staticmethod
    def is_valid_custom_code(code: str, min_length: int = 3, 
                           max_length: int = 20) -> Tuple[bool, str]:
        """
        Kullanıcı tanımlı kısa kodun geçerli olup olmadığını kontrol eder
        
        Args:
            code (str): Kontrol edilecek kod
            min_length (int): Minimum uzunluk
            max_length (int): Maksimum uzunluk
            
        Returns:
            Tuple[bool, str]: (geçerli_mi, hata_mesajı)
        """
        if not code or not isinstance(code, str):
            return False, "Kod boş olamaz"
        
        # Uzunluk kontrolü
        if len(code) < min_length:
            return False, f"Kod en az {min_length} karakter olmalı"
        
        if len(code) > max_length:
            return False, f"Kod en fazla {max_length} karakter olabilir"
        
        # Karakter kontrolü (alfanumerik + dash/underscore)
        if not re.match(r'^[a-zA-Z0-9_-]+$', code):
            return False, "Kod sadece harf, rakam, tire (-) ve alt çizgi (_) içerebilir"
        
        # Başlangıç kontrolü (rakam ile başlayamaz)
        if code[0].isdigit():
            return False, "Kod rakam ile başlayamaz"
        
        # Yasaklı kelime kontrolü
        if code.lower() in CodeValidator.RESERVED_WORDS:
            return False, f"'{code}' rezerve edilmiş bir kelimedir"
        
        # Üst üste gelen karakterler kontrolü
        if re.search(r'(.)\1{3,}', code):  # 4+ aynı karakter
            return False, "Üst üste 4'ten fazla aynı karakter kullanılamaz"
        
        return True, ""


class StatisticsHelper:
    """
    İstatistik hesaplama yardımcı fonksiyonları
    """
    
    @staticmethod
    def calculate_click_rate(total_urls: int, total_clicks: int) -> float:
        """
        Ortalama tıklama oranını hesaplar
        
        Args:
            total_urls (int): Toplam URL sayısı
            total_clicks (int): Toplam tıklama sayısı
            
        Returns:
            float: Ortalama tıklama oranı
        """
        return total_clicks / total_urls if total_urls > 0 else 0.0
    
    @staticmethod
    def get_popular_domains(urls_data: List[Dict]) -> Dict[str, int]:
        """
        En popüler domain'leri analiz eder
        
        Args:
            urls_data (List[Dict]): URL verilerini içeren liste
            
        Returns:
            Dict[str, int]: Domain -> sayı mapping'i
        """
        domain_counts = {}
        
        for url_data in urls_data:
            try:
                original_url = url_data.get('original_url', '')
                domain = urlparse(original_url).netloc.lower()
                
                if domain:
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
            except:
                continue  # Hatalı URL'leri atla
        
        # Sayıya göre sırala
        return dict(sorted(domain_counts.items(), key=lambda x: x[1], reverse=True))
    
    @staticmethod
    def get_time_based_stats(urls_data: List[Dict], 
                           days: int = 30) -> Dict[str, int]:
        """
        Zaman bazlı istatistikleri hesaplar
        
        Args:
            urls_data (List[Dict]): URL verilerini içeren liste
            days (int): Kaç günlük veri analiz edilecek
            
        Returns:
            Dict[str, int]: Tarih -> sayı mapping'i
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        daily_stats = {}
        
        for url_data in urls_data:
            try:
                created_str = url_data.get('created_at', '')
                if created_str:
                    created_date = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                    
                    if created_date >= cutoff_date:
                        date_key = created_date.strftime('%Y-%m-%d')
                        daily_stats[date_key] = daily_stats.get(date_key, 0) + 1
            except:
                continue  # Hatalı tarih'leri atla
        
        return daily_stats


# Global instances (app.py'da kullanım için)
url_shortener = URLShortener()
url_validator = URLValidator()
code_validator = CodeValidator()
stats_helper = StatisticsHelper()


def create_short_url(original_url: str, custom_code: str = None, 
                    existing_codes: set = None) -> Tuple[bool, str, str]:
    """
    Kısa URL oluşturma ana fonksiyonu
    
    Bu fonksiyon tüm validation ve generation işlemlerini koordine eder.
    
    Args:
        original_url (str): Orijinal uzun URL
        custom_code (str, optional): Kullanıcı tanımlı kod
        existing_codes (set, optional): Mevcut kodlar (çakışma kontrolü için)
        
    Returns:
        Tuple[bool, str, str]: (başarılı_mı, kısa_kod, hata_mesajı)
    """
    existing_codes = existing_codes or set()
    
    # URL doğrulama
    is_valid, error_msg = url_validator.is_valid_url(original_url)
    if not is_valid:
        return False, "", f"URL Hatası: {error_msg}"
    
    # URL'yi normalize et
    normalized_url = url_validator.normalize_url(original_url)
    
    # Custom kod kontrolü
    if custom_code:
        is_valid, error_msg = code_validator.is_valid_custom_code(custom_code)
        if not is_valid:
            return False, "", f"Kod Hatası: {error_msg}"
        
        if custom_code in existing_codes:
            return False, "", "Bu kod zaten kullanılıyor"
        
        return True, custom_code, ""
    
    # Otomatik kod üretimi
    short_code = url_shortener.generate_unique_code(normalized_url, existing_codes)
    
    if not short_code:
        return False, "", "Benzersiz kod üretilemedi, lütfen tekrar deneyin"
    
    return True, short_code, ""


def format_click_count(count: int) -> str:
    """
    Tıklama sayısını kullanıcı dostu formatta gösterir
    
    Args:
        count (int): Tıklama sayısı
        
    Returns:
        str: Formatlanmış sayı (örn: "1.2K", "3.4M")
    """
    if count < 1000:
        return str(count)
    elif count < 1000000:
        return f"{count/1000:.1f}K"
    elif count < 1000000000:
        return f"{count/1000000:.1f}M"
    else:
        return f"{count/1000000000:.1f}B"


def get_domain_from_url(url: str) -> str:
    """
    URL'den domain adını çıkarır
    
    Args:
        url (str): URL
        
    Returns:
        str: Domain adı veya boş string
    """
    try:
        return urlparse(url).netloc.lower()
    except:
        return ""


if __name__ == "__main__":
    # Utility fonksiyonlarını test et
    print("🧪 Utils Test Ediliyor...\n")
    
    # URL Shortener test
    shortener = URLShortener()
    test_url = "https://www.example.com/very/long/path"
    
    print("📏 URL Shortener:")
    print(f"   Random Code: {shortener.generate_random_code()}")
    print(f"   Hash Code: {shortener.generate_hash_based_code(test_url)}")
    print()
    
    # URL Validator test
    print("✅ URL Validator:")
    valid_urls = [
        "https://www.google.com",
        "http://example.com/path",
        "https://github.com/user/repo"
    ]
    
    for url in valid_urls:
        is_valid, msg = URLValidator.is_valid_url(url)
        print(f"   {url}: {'✅' if is_valid else '❌'} {msg}")
    print()
    
    # Code Validator test
    print("🔤 Code Validator:")
    test_codes = ["mycode", "admin", "a", "valid-code_123"]
    
    for code in test_codes:
        is_valid, msg = CodeValidator.is_valid_custom_code(code)
        print(f"   '{code}': {'✅' if is_valid else '❌'} {msg}")
    print()
    
    print("✅ Tüm utility'ler test edildi!")