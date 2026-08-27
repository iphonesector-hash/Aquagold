/* AquaGold premium interaction layer: graphical icons, resilient navigation and field shortcuts. */
(() => {
  const previous = window.app;
  if (typeof previous !== 'function') return;

  const ICON_BY_PAGE = {
    dashboard: 'home', daily: 'daily', customers: 'customers', services: 'services',
    map: 'map', expense: 'expenses', finance: 'finance', insights: 'insights',
    smart: 'smart', reminders: 'reminders', settings: 'settings', products: 'products', 'aqua-ai': 'smart', 'bale-jobs': 'services',
    invoices: 'invoices', 'customer-edit': 'customers', 'customer-detail': 'customers',
    'new-service': 'services', 'product-edit': 'products', 'invoice-new': 'invoices',
    'invoice-view': 'invoices'
  };
  const ICONS = new Set([
    'home', 'daily', 'customers', 'services', 'map', 'expenses', 'finance', 'insights',
    'smart', 'reminders', 'settings', 'products', 'invoices', 'search', 'support', 'more',
    'voice', 'route', 'theme', 'logout', 'sync', 'plus', 'close', 'edit', 'download',
    'print', 'gps', 'copy', 'camera', 'lock', 'heatmap', 'share'
  ]);

  const distanceMeters = (a, b, c, d) => {
    const radius = 6371000;
    const p = Math.PI / 180;
    const x = (c - a) * p;
    const y = (d - b) * p;
    const h = Math.sin(x / 2) ** 2 + Math.cos(a * p) * Math.cos(c * p) * Math.sin(y / 2) ** 2;
    return 2 * radius * Math.asin(Math.sqrt(h));
  };

  window.app = function premiumApp() {
    const state = previous();
    state.navs = state.navs.map(item => ({...item, icon: ICON_BY_PAGE[item.id] || item.icon || 'more'}));
    Object.assign(state, {
      premiumReady: false,
      listening: false,
      speechSupported: Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
      quickActions: [
        {id: 'customers', label: 'مشتری‌ها', caption: 'پرونده و سوابق', icon: 'customers', tone: 'cyan'},
        {id: 'services', label: 'سرویس‌ها', caption: 'ثبت و پیگیری', icon: 'services', tone: 'silver'},
        {id: 'smart', label: 'ثبت هوشمند', caption: 'متن، صدا و GPS', icon: 'smart', tone: 'azure'},
        {id: 'invoices', label: 'فاکتورها', caption: 'صدور و ارسال', icon: 'invoices', tone: 'gold'},
        {id: 'products', label: 'محصولات', caption: 'کاتالوگ و قیمت', icon: 'products', tone: 'ice'},
        {id: 'finance', label: 'گزارش مالی', caption: 'سود و تسویه', icon: 'finance', tone: 'blue'},
        {id: 'map', label: 'نقشه', caption: 'مشتری و مسیر', icon: 'map', tone: 'aqua'},
        {id: 'settings', label: 'تنظیمات', caption: 'امنیت و بکاپ', icon: 'settings', tone: 'steel'},
        {id: 'bale-jobs', label: 'کارهای جدید', caption: 'ورودی مستقیم از بله', icon: 'services', tone: 'cyan'},
        {id: 'aqua-ai', label: 'هوش مصنوعی آکوا', caption: 'چت، صدا و فرمان', icon: 'smart', tone: 'azure'}
      ]
    });

    Object.defineProperties(state, {
      nearbyCustomerCount: {
        configurable: true,
        get() {
          if (this.nearby?.length) return this.nearby.length;
          const located = this.customers.filter(c => c.latitude && c.longitude);
          if (!this.gps?.lat || !this.gps?.lng) return located.length;
          return located.filter(c => distanceMeters(
            Number(this.gps.lat), Number(this.gps.lng), Number(c.latitude), Number(c.longitude)
          ) <= 5000).length;
        }
      },
      dashboardAlerts: {
        configurable: true,
        get() {
          const debt = this.jobs.filter(j => Number(j.customer_balance || 0) > 0).length;
          const missingGps = this.customers.filter(c => !c.latitude || !c.longitude).length;
          return [
            {label: 'موعد سرویس', value: this.reminders.length, page: 'reminders', icon: 'reminders'},
            {label: 'مانده حساب', value: debt, page: 'services', icon: 'invoices'},
            {label: 'بدون GPS', value: missingGps, page: 'customers', icon: 'gps'}
          ];
        }
      }
    });

    state.icon = function icon(name, className = '') {
      const safe = ICONS.has(name) ? name : 'more';
      return `<svg class="aq-svg ${className}" aria-hidden="true" focusable="false"><use href="/assets/aqua-icons.svg?v=20260826-1#i-${safe}"></use></svg>`;
    };
    state.roleLabel = function roleLabel(role) {
      return ({viewer: 'مشاهده‌گر', technician: 'کارشناس سرویس', admin: 'مدیر سیستم', superadmin: 'مدیر ارشد'})[role] || 'کاربر AquaGold';
    };
    state.runQuick = async function runQuick(action) {
      navigator.vibrate?.(8);
      if (action.id === 'services') return this.go('new-service');
      return this.go(action.id);
    };
    state.startVoiceIntake = function startVoiceIntake() {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) return this.toast('ثبت صوتی در این مرورگر پشتیبانی نمی‌شود', 'error');
      if (this.listening) return;
      this.page = 'smart';
      const recognition = new Recognition();
      recognition.lang = 'fa-IR';
      recognition.interimResults = false;
      recognition.continuous = false;
      recognition.onstart = () => {
        this.listening = true;
        this.toast('گوش می‌دهم؛ اطلاعات سرویس را بگو', 'info');
      };
      recognition.onresult = event => {
        const text = Array.from(event.results).map(result => result[0]?.transcript || '').join(' ').trim();
        if (text) this.smartText = [this.smartText, text].filter(Boolean).join('\n');
      };
      recognition.onerror = event => {
        if (event.error !== 'aborted') this.toast('صدای واضح دریافت نشد؛ دوباره امتحان کن', 'error');
      };
      recognition.onend = () => { this.listening = false; };
      try { recognition.start(); } catch { this.listening = false; }
    };
    state.copyTodaySummary = function copyTodaySummary() {
      const today = this.stats.today || {};
      this.copyText([
        `گزارش امروز AquaGold — ${this.persianDate(new Date())}`,
        `دریافتی: ${this.money(today.received)} تومان`,
        `سهم شرکت: ${this.money(today.company_share)} تومان`,
        `هزینه: ${this.money(today.expenses)} تومان`,
        `سود خالص: ${this.money(today.net_profit)} تومان`
      ].join('\n'));
    };

    const originalGo = state.go.bind(state);
    state.go = async function resilientGo(page) {
      this.page = page;
      window.scrollTo({top: 0, behavior: 'smooth'});
      try {
        await originalGo(page);
      } catch (error) {
        this.toast(error?.message || 'اطلاعات این بخش تازه نشد؛ دوباره تلاش کن', 'error');
      }
    };

    const originalInit = state.init.bind(state);
    state.init = async function premiumInit() {
      try {
        await originalInit();
      } finally {
        this.premiumReady = true;
        document.documentElement.dataset.theme ||= 'dark';
        if (this.token) {
          [80, 240, 700].forEach(delay => setTimeout(() => {
            this.mountEnhancements?.();
            this.mountCommerce?.();
          }, delay));
        }
      }
    };
    return state;
  };
})();
