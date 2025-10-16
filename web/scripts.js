// --- ЗАГАЛЬНІ НАЛАШТУВАННЯ ---
// все запросы идут через nginx (http://<IP>:8080)
const SEARCH_API_URL = '/search';
const CHAT_SEARCH_API_URL = '/chat/search';
const CHAT_SEARCH_SSE_URL = '/chat/search/sse';
// Feature flags
const FEATURE_CHAT_AUTOSCROLL = true; // авто-скрол до каруселі (ON за замовчуванням)
let FEATURE_CHAT_STREAMING = false; // за замовчуванням OFF, може вмикатись через /config
// Persistence keys
const WELCOME_SEEN_KEY = 'welcome_seen';
const CHAT_WELCOME_SEEN_KEY = 'chat_welcome_seen';

// ChatGPT тепер через backend API
const CHAT_API_URL = '/api/chat/advice';
const TA_DA_API_TOKEN = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpIjoiNTM2NDg3MzAiLCJzIjo4MDk2NzgzMzgyMDQ2MTd9.PZx337yjQl5xX0FPv-scK4wPzuzMZ1zTWTrLoaTI3iY";

// Схема категорій (синхронізована з backend) - розширена версія на основі асортименту TA-DA
const CATEGORY_SCHEMA = {
  // Одяг
  "clothes_tshirts": {"label": "Футболки"},
  "clothes_shirts": {"label": "Сорочки"},
  "clothes_pants": {"label": "Штани"},
  "clothes_shorts": {"label": "Шорти"},
  "clothes_dresses": {"label": "Сукні"},
  "clothes_skirts": {"label": "Спідниці"},
  "clothes_sweaters": {"label": "Светри/Худі"},
  "clothes_outerwear": {"label": "Куртки/Пальта"},
  "clothes_underwear": {"label": "Білизна/Шкарпетки"},
  "clothes_sleepwear": {"label": "Піжами/Домашній одяг"},
  "clothes_accessories": {"label": "Аксесуари для одягу"},
  "clothes_shoes": {"label": "Взуття"},
  // Іграшки та ігри
  "toys_water": {"label": "Для плавання та води"},
  "toys_general": {"label": "Іграшки"},
  "toys_educational": {"label": "Розвиваючі іграшки"},
  "games_board": {"label": "Настільні ігри"},
  "toys_outdoor": {"label": "Для активного відпочинку"},
  // Кухня та посуд
  "house_kitchen_cookware": {"label": "Кухонний посуд"},
  "house_kitchen_tableware": {"label": "Посуд для сервірування"},
  "house_kitchen_cutlery": {"label": "Столові прибори"},
  "house_kitchen_tools": {"label": "Кухонні аксесуари"},
  "house_kitchen_storage": {"label": "Ємності для зберігання"},
  "house_kitchen_textiles": {"label": "Кухонний текстиль"},
  // Прибирання та господарські товари
  "house_cleaning_tools": {"label": "Інвентар для прибирання"},
  "house_cleaning_chemicals": {"label": "Побутова хімія"},
  "house_cleaning_bathroom": {"label": "Для ванної кімнати"},
  "house_laundry": {"label": "Для прання"},
  // Косметика та гігієна
  "cosmetics_skincare": {"label": "Догляд за шкірою"},
  "cosmetics_suncare": {"label": "Сонцезахисні засоби"},
  "cosmetics_body": {"label": "Догляд за тілом"},
  "cosmetics_oral": {"label": "Гігієна порожнини рота"},
  "cosmetics_firstaid": {"label": "Аптечка"},
  // Канцелярія
  "stationery_notebooks": {"label": "Зошити та блокноти"},
  "stationery_paper": {"label": "Папір"},
  "stationery_writing": {"label": "Ручки та олівці"},
  "stationery_cases": {"label": "Пенали та папки"},
  "stationery_art": {"label": "Товари для творчості"},
  "stationery_office": {"label": "Офісні товари"},
  // Товари для дому
  "home_decor": {"label": "Декор та прикраси"},
  "home_textiles": {"label": "Домашній текстиль"},
  "home_storage": {"label": "Організація та зберігання"},
  "home_lighting": {"label": "Освітлення"},
  "home_electronics": {"label": "Побутова електроніка"},
  "home_garden": {"label": "Для саду та городу"},
  // Сезонні товари
  "seasonal_summer": {"label": "Літні товари"},
  "seasonal_winter": {"label": "Зимові товари"},
  "seasonal_holiday": {"label": "Святкові товари"},
  "seasonal_bbq": {"label": "Для пікніка та барбекю"},
  // Інше
  "home_insects": {"label": "Від комах"},
  "auto_accessories": {"label": "Автотовари"},
  "pet_supplies": {"label": "Для тварин"}
};

// DOM та стан
const pages = { welcome: document.getElementById('welcomePage'), simple: document.getElementById('simpleSearchPage'), chat: document.getElementById('chatSearchPage') };
// Змінні для пошукових елементів
const headerSearchInput = document.getElementById('headerSearchInput');
const chatSearchInput = document.getElementById('chatSearchInput');
const chatSearchButton = document.getElementById('chatSearchButton');
const resultsDivs = { simple: document.getElementById('results-simple') };
const cartElement = document.getElementById('full-cart');
const cartItemsElement = document.getElementById('full-cart-items-list');
const chatThread = document.getElementById('chatThread');

let cartItems = [];
let chatStep = 0; // лічильник кроків (для відміток "Крок N")
let chatDialogContext = null; // зберігаємо dialog_context від бекенда між раундами
let userHasMinimizedCart = false; // чи користувач вже згортав кошик
let searchBoxAnimationShown = false; // чи вже була показана анімація переміщення пошукової строки
let userHasEverAddedItems = false; // чи користувач коли-небудь додавав товари
let priceCache = new Map(); // кеш цін для уникнення повторних запитів
let productsWithPrices = new Map(); // Зберігаємо товари з цінами
let welcomeGreetingShown = false; // чи вже було показано привітальне повідомлення GPT
let welcomeMessageMoved = false; // чи вже було переміщено привітальне повідомлення після пошуку
let welcomeTypingComplete = false; // чи завершено друк привітального повідомлення

// --- Допоміжний лог назв товарів з БД ---
function logProductTitles(label, products) {
  try {
    if (!Array.isArray(products) || products.length === 0) {
      console.log(`[products] ${label}: <empty>`);
      return;
    }
    const titles = products.map(p => (p?.title_ua || p?.title_ru || p?.title || 'Без назви'));
    console.log(`[products] ${label}:`, titles);
  } catch (_) {}
}

// Історія пошуків для контексту (тільки в пам'яті, очищається при перезавантаженні)
let searchHistory = [];
const MAX_HISTORY_ITEMS = 5; // Максимум 5 останніх пошуків
const SEARCH_HISTORY_KEY = 'search_history'; // Ключ для очищення старих даних

// Система лімітів для чат-пошуку
const CHAT_SEARCH_LIMIT = 15; // Максимум запитів
const CHAT_SEARCH_WINDOW = 15 * 60 * 1000; // 15 хвилин в мілісекундах
const CHAT_SEARCH_LIMIT_KEY = 'chat_search_limit_data';

// Приховуємо кнопку замовлення при завантаженні сторінки
document.addEventListener('DOMContentLoaded', function() {
  const checkoutBtn = document.getElementById('checkout-btn');
  if(checkoutBtn) checkoutBtn.style.display = 'none';
  
  // Очищаємо старі дані з localStorage та sessionStorage (якщо вони там є)
  try {
    localStorage.removeItem(SEARCH_HISTORY_KEY);
    sessionStorage.removeItem(SEARCH_HISTORY_KEY);
    console.log('✅ Історію очищено - починаємо нову сесію');
  } catch(e) {
    console.warn('Failed to clear storage history:', e);
  }
  
  // НЕ завантажуємо історію - кожне перезавантаження = нова сесія
  searchHistory = [];
  console.log('📜 Початок нової сесії - історія порожня');
  
  // Перевіряємо ліміт запитів при завантаженні
  const limitCheck = checkChatSearchLimit();
  console.log('🔒 Статус лімітів при завантаженні:', limitCheck);
  
  // Запускаємо typewriter анімацію для пошукової строки
  startTypewriter();
  
  // Стартова сторінка завжди welcome (до першого пошуку в поточному завантаженні)
  if (pages.welcome) {
    switchPage('welcome');
  }

  // Синхронізуємо стан іконок при завантаженні
  syncHeaderSearchIcons();

  // Якщо чат-вітання вже було приховано раніше — приховуємо його і інпут назавжди
  try {
    // Після перезавантаження сторінки показуємо чат-вітання знову
    sessionStorage.removeItem(CHAT_WELCOME_SEEN_KEY);
    const chatWelcomeSeen = sessionStorage.getItem(CHAT_WELCOME_SEEN_KEY) === '1';
    if (chatWelcomeSeen) {
      const chatWelcome = document.querySelector('#chatSearchPage .chat-welcome');
      if (chatWelcome) chatWelcome.style.display = 'none';
      const mainSearchBox = document.querySelector('#chatSearchPage #mainChatSearchBox');
      if (mainSearchBox) mainSearchBox.style.display = 'none';
    }
  } catch (_) { /* ignore storage errors */ }
  
  // Скидаємо флаги привітального повідомлення при перезавантаженні сторінки
  welcomeGreetingShown = false;
  welcomeMessageMoved = false;
  welcomeTypingComplete = false;
});

// Ховає чат-вітання і головний інпут, опційно виставляє прапорець
function hideChatIntro(setFlag = false){
  try { if (setFlag) sessionStorage.setItem(CHAT_WELCOME_SEEN_KEY, '1'); } catch(_) {}
  const chatWelcome = document.querySelector('#chatSearchPage .chat-welcome');
  if (chatWelcome) chatWelcome.style.display = 'none';
  const mainSearchBox = document.querySelector('#chatSearchPage #mainChatSearchBox');
  if (mainSearchBox) mainSearchBox.style.display = 'none';
  
  // Ховаємо швидкі кнопки після першого пошуку
  const quickButtons = document.getElementById('quickSearchButtons');
  if (quickButtons) quickButtons.style.display = 'none';
}

// --- Кошик ---
function getProductId(product) {
  return product.id || product.uuid;
}

async function toggleCartItem(product){
  // Перевіряємо наявність товару перед додаванням
  if (!product.good_code) {
    return; // Просто виходимо без alert
  }
  
  const productId = getProductId(product);
  const idx = cartItems.findIndex(i=>getProductId(i.product)===productId);
  
  if(idx>-1){
    cartItems.splice(idx,1);
  } else {
    cartItems.push({product,quantity:1});
    userHasEverAddedItems = true; // користувач додав товар
    
    // Показуємо міні-корзину
    showMiniCart(product);
  }
  renderCart();
  
  // Оновлюємо повну корзину
  if(idx>-1){
    // Товар видаляється - оновлюємо всю корзину
    renderFullCart();
  } else {
    // Товар додається - додаємо тільки його до повної корзини
    addItemToFullCart(product);
  }
  
  updateCartTotals(); // Оновлюємо загальну ціну
  updateSelectedCards();
  updateCartBadge(); // Оновлюємо бейдж в хедері
}
function changeQuantity(productId,delta){
  const item = cartItems.find(i=>getProductId(i.product)===productId);
  if(item){
    item.quantity += delta;
    if(item.quantity<=0){ 
      cartItems = cartItems.filter(i=>getProductId(i.product)!==productId);
      
      // Видаляємо елемент з DOM
      const itemCard = document.querySelector(`[data-product-id="${productId}"]`);
      if (itemCard) {
        itemCard.remove();
      }
      
      if (cartItems.length === 0) {
        hideFullCart();
        // Показуємо повідомлення про порожню корзину
        const itemsList = document.getElementById('full-cart-items-list');
        if (itemsList) {
          itemsList.innerHTML = '<p class="empty-cart-message">Кошик порожній</p>';
        }
      } else {
        // Оновлюємо повну корзину тільки коли товар видаляється
        renderFullCart();
      }
    } else {
      // Оновлюємо кількість для конкретного товару
      const itemCard = document.querySelector(`[data-product-id="${productId}"]`);
      if (itemCard) {
        const quantityDisplay = itemCard.querySelector('.quantity-display');
        if (quantityDisplay) {
          quantityDisplay.textContent = item.quantity;
        }
        
        // Оновлюємо загальну ціну для конкретного товару
        const price = parseFloat(item.product.price) || 0;
        const itemTotal = price * item.quantity;
        const totalAmount = itemCard.querySelector('.cart-item-total-amount');
        if (totalAmount) {
          totalAmount.textContent = `${itemTotal.toFixed(2)} ₴`;
        }
      }
    }
    
    // Оновлюємо загальний підсумок
    updateCartTotals();
    
    renderCart();
    renderFullCart(); // Повертаємо renderFullCart для зміни кількості, щоб товари не згорталися
    updateSelectedCards();
    updateCartBadge();
  }
}

function renderCart(){
  if (!cartItemsElement) {
    return;
  }
  
  cartItemsElement.innerHTML='';
  const totalItems = cartItems.reduce((sum, item) => sum + item.quantity, 0);
  
  // Оновлюємо бейдж в хедері
  const headerBadge = document.getElementById('headerCartBadge');
  if(totalItems > 0){
    headerBadge.textContent = totalItems;
    headerBadge.classList.add('visible');
  } else {
    headerBadge.classList.remove('visible');
  }


  if(cartItems.length>0){
    cartItems.forEach(item=>{
      const div=document.createElement('div');
      div.className='cart-item';
      const title=item.product.title_ua||'Без назви';
      div.innerHTML=`
        <div class="cart-item-info"><span>${title}</span></div>
        <div class="cart-item-controls">
          <button onclick="changeQuantity('${getProductId(item.product)}',-1)">-</button>
          <span>${item.quantity}</span>
          <button onclick="changeQuantity('${getProductId(item.product)}',1)">+</button>
        </div>`;
      cartItemsElement.appendChild(div);
    });
    
    // Показуємо секцію з підсумком коли є товари
    const cartSummary = document.getElementById('cart-summary');
    if(cartSummary) cartSummary.style.display = 'block';
    
    // Автоматично розгортаємо тільки якщо користувач ще не згортав кошик
    if(!userHasMinimizedCart && cartElement){
      cartElement.classList.add('visible');
    }
  }else{
    // Показуємо повідомлення про порожню корзину
    cartItemsElement.innerHTML = '<p style="color: var(--text-light); text-align: center;">Кошик порожній</p>';
    
    // Приховуємо секцію з підсумком коли кошик пустий
    const cartSummary = document.getElementById('cart-summary');
    if(cartSummary) cartSummary.style.display = 'none';
    
    // Якщо користувач коли-небудь додавав товари - автоматично закриваємо
    if(userHasEverAddedItems && cartElement){
      cartElement.classList.remove('visible');
    }
    
    userHasMinimizedCart = false; // скидаємо при видаленні всіх товарів
  }
  updateSelectedCards();
  calculateCartTotal();
}


async function getProductPrice(goodCode) {
  // Перевіряємо валідність goodCode
  if (!goodCode || goodCode === 'undefined' || goodCode === 'null') {
    return 0;
  }
  
  // Перевіряємо кеш
  if (priceCache.has(goodCode)) {
    return priceCache.get(goodCode);
  }
  
  try {
    const response = await fetch('/api/ta-da/find.gcode', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': TA_DA_API_TOKEN,
        'User-Language': 'ua'
      },
      body: JSON.stringify({ shop_id: "8", good_code: goodCode })
    });
    
    if (!response.ok) {
      // Тихо обробляємо помилки API
      return 0;
    }
    
    const data = await response.json();
    
    // Перевіряємо на fallback відповідь
    if (data.error) {
      return 0;
    }
    
    // Округлюємо ціну до 2 знаків після коми
    const price = data.price ? parseFloat(data.price).toFixed(2) : 0;
    // Зберігаємо в кеш
    priceCache.set(goodCode, price);
    return price;
  } catch (error) {
    // Тихо обробляємо помилки API, не логуємо в консоль
    return 0;
  }
}

async function calculateCartTotal() {
  const cartTotalElement = document.getElementById('cartTotal');
  if (!cartTotalElement) return;
  
  if (cartItems.length === 0) {
    cartTotalElement.textContent = '0.00 ₴';
    return;
  }
  
  let totalSum = 0;
  // Виконуємо всі запити цін паралельно
  const pricePromises = cartItems.map(async (item) => {
    const price = await getProductPrice(item.product.good_code);
    return price * item.quantity;
  });
  
  const prices = await Promise.all(pricePromises);
  totalSum = prices.reduce((sum, price) => sum + parseFloat(price), 0);
  
  cartTotalElement.textContent = `${totalSum.toFixed(2)} ₴`;
}

function clearCart() {
  if (cartItems.length === 0) return;
  
  cartItems = [];
  renderCart();
  renderFullCart(); // Оновлюємо повну корзину
  updateSelectedCards();
}

function updateSelectedCards(){
  const productCards=document.querySelectorAll('.product-card');
  const ids=cartItems.map(i=>getProductId(i.product));
  
  productCards.forEach((card, index)=>{ 
    const cardId = card.dataset.id || card.dataset.uuid;
    const isSelected = ids.includes(cardId);
    
    if (isSelected) {
      card.classList.add('selected');
      
      // Оновлюємо текст кнопки на "Прибрати"
      const addToCartBtn = card.querySelector('.add-to-cart-btn');
      if (addToCartBtn && !addToCartBtn.disabled) {
        addToCartBtn.textContent = 'Прибрати';
        addToCartBtn.style.background = '#dc3545'; // Червоний колір для кнопки видалення
      }
    } else {
      card.classList.remove('selected');
      
      // Оновлюємо текст кнопки на "Купити"
      const addToCartBtn = card.querySelector('.add-to-cart-btn');
      if (addToCartBtn && !addToCartBtn.disabled) {
        addToCartBtn.textContent = 'Купити';
        addToCartBtn.style.background = ''; // Повертаємо оригінальний колір
      }
    }
  });
  updateCartBadge(); // Оновлюємо бейдж при оновленні вибраних карток
}

// Функції для роботи з кошиком
function toggleCart(){
  // Відкриваємо повну корзину замість старої
  showFullCart();
}

// --- Функції для прогресу ---
function updateProgress(container, percentage) {
  const progressBar = container.querySelector('.progress-bar');
  if (progressBar) {
    progressBar.style.width = percentage + '%';
  }
  // Маркери прибрані — нічого не підсвічуємо
  // Текст поточного етапу
  const stageEl = container.querySelector('.current-stage');
  if (stageEl) {
    let label = '';
    if (percentage < 20) label = '';
    else if (percentage < 40) label = 'Аналіз запиту';
    else if (percentage < 60) label = 'Пошук у каталозі';
    else if (percentage < 75) label = 'Фільтрація результатів';
    else if (percentage < 90) label = 'Групування за категоріями';
    else if (percentage < 100) label = 'Формування рекомендацій';
    else label = '';
    stageEl.textContent = label;
  }
}

// Оновити прогрес і примусово встановити підпис етапу
function updateProgressWithLabel(container, percentage, label) {
  updateProgress(container, percentage);
  const stageEl = container.querySelector('.current-stage');
  if (stageEl && typeof label === 'string') {
    stageEl.textContent = label;
  }
}

function createProgressLoader() {
  return `
    <div class="loading-container">
      <div class="progress-loader">
        <div class="progress-bar" style="width: 0%"></div>
      </div>
      <div class="loading-text">
        <p>Шукаю товари...</p>
        <p class="loading-subtitle">Зачекайте, поки AI знайде найкращі товари для вас.</p>
      </div>
    </div>
  `;
}

// --- Простий пошук ---
async function performSimpleSearch(){
  const query = headerSearchInput.value.trim();
  if(query.length === 0 || query.split(/\s+/).length === 0){ return; }
  
  // Після першого будь-якого пошуку більше не показуємо вітальну сторінку
  sessionStorage.setItem(WELCOME_SEEN_KEY, '1');
  
  // Гарантуємо що ми на сторінці простого пошуку
  if (!pages.simple.classList.contains('active')) {
    switchPage('simple');
  }
  
  resultsDivs.simple.innerHTML = createProgressLoader();
  
  try{
    // Прогрес: 20% - початок пошуку
    updateProgress(resultsDivs.simple, 20);
    
    // Невелика затримка для показу прогресу
    await new Promise(resolve => setTimeout(resolve, 200));
    // Прогрес: 40% - підготовка запиту
    updateProgress(resultsDivs.simple, 40);
    
    // Використовуємо нові параметри: більше результатів та мінімальний score
    const searchParams = {
      query: query,
      k: 100, // Максимум 100 товарів
      min_score: 0.1 // Мінімальний поріг релевантності
    };
    
    // Прогрес: 60% - відправка запиту
    updateProgress(resultsDivs.simple, 60);
    
    const res = await fetch(SEARCH_API_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(searchParams)});
    
    // Прогрес: 80% - отримання відповіді
    updateProgress(resultsDivs.simple, 80);
    
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || `Помилка сервера: ${res.status}`);
    
    // Прогрес: 90% - обробка результатів
    updateProgress(resultsDivs.simple, 90);
    
    const allProducts = data.results || [];
    // Лог назв товарів (простий пошук)
    logProductTitles('simple-search', allProducts);
    if(allProducts.length === 0){
      resultsDivs.simple.innerHTML = '<div class="result-placeholder"><p>Нічого не знайдено.</p></div>';
      return;
    }

    // Прогрес: 100% - завершення
    updateProgress(resultsDivs.simple, 100);
    
    // Невелика затримка для показу завершення
    await new Promise(resolve => setTimeout(resolve, 300));

    // Показуємо всі релевантні товари (вже відсортовані за score)
    displaySimpleResults(allProducts);
  }catch(e){
    resultsDivs.simple.innerHTML = `<div class="result-placeholder"><p style="color:red;">Помилка: ${e.message}</p></div>`;
  }
}

// --- Функції для роботи з історією ---
function getSearchHistory() {
  return searchHistory;
}

// --- MEMORY-ONLY HISTORY MANAGEMENT ---
// Історія зберігається тільки в пам'яті - очищається при перезавантаженні сторінки
function loadSearchHistoryFromStorage() { 
  // Більше не завантажуємо з storage - історія тільки в пам'яті
  searchHistory = [];
}

function saveSearchHistoryToStorage() {
  // Більше не зберігаємо в storage - історія тільки в пам'яті
  // Це забезпечує очищення при кожному перезавантаженні
}

function addToSearchHistory(query) {
  if (!query || typeof query !== 'string' || query.trim().length === 0) return;
  
  const historyItem = {
    query: query.trim(),
    timestamp: new Date().toISOString()
  };
  
  // Видаляємо дублікати (останній запит якщо такий самий)
  if (searchHistory.length > 0 && searchHistory[searchHistory.length - 1].query === historyItem.query) {
    return;
  }
  
  searchHistory.push(historyItem);
  
  // Обмежуємо розмір історії
  if (searchHistory.length > MAX_HISTORY_ITEMS) {
    searchHistory = searchHistory.slice(-MAX_HISTORY_ITEMS);
  }
  
  saveSearchHistoryToStorage();
}

function clearSearchHistory() { 
  searchHistory = []; 
  console.log('🗑️ Історія пошуків очищена (пам\'ять)');
}

// --- СИСТЕМА ЛІМІТІВ ЧАТ-ПОШУКУ ---
function getChatSearchLimitData() {
  try {
    const stored = localStorage.getItem(CHAT_SEARCH_LIMIT_KEY);
    if (stored) {
      const data = JSON.parse(stored);
      // Видаляємо старі запити (старіші за 15 хвилин)
      const now = Date.now();
      data.searches = data.searches.filter(timestamp => (now - timestamp) < CHAT_SEARCH_WINDOW);
      return data;
    }
  } catch (e) {
    console.warn('Failed to load chat search limit data:', e);
  }
  return { searches: [] };
}

function saveChatSearchLimitData(data) {
  try {
    localStorage.setItem(CHAT_SEARCH_LIMIT_KEY, JSON.stringify(data));
  } catch (e) {
    console.warn('Failed to save chat search limit data:', e);
  }
}

function checkChatSearchLimit() {
  const data = getChatSearchLimitData();
  const remaining = CHAT_SEARCH_LIMIT - data.searches.length;
  
  if (remaining <= 0) {
    // Знаходимо найстаріший запит для визначення часу очікування
    const oldestSearch = Math.min(...data.searches);
    const timeUntilReset = CHAT_SEARCH_WINDOW - (Date.now() - oldestSearch);
    const minutesLeft = Math.ceil(timeUntilReset / 60000);
    
    return {
      allowed: false,
      remaining: 0,
      minutesLeft: minutesLeft
    };
  }
  
  return {
    allowed: true,
    remaining: remaining,
    minutesLeft: 0
  };
}

function recordChatSearchRequest() {
  const data = getChatSearchLimitData();
  data.searches.push(Date.now());
  saveChatSearchLimitData(data);
  console.log('📊 Записано запит. Залишилось:', CHAT_SEARCH_LIMIT - data.searches.length);
}

function showChatSearchLimitMessage(minutesLeft) {
  // Ховаємо пошукову строку
  const searchBox = document.getElementById('chatSearchBox');
  if (searchBox) {
    searchBox.style.display = 'none';
  }
  
  // Ховаємо швидкі кнопки та приклади
  const quickButtons = document.getElementById('quickSearchButtons');
  if (quickButtons) quickButtons.style.display = 'none';
  
  const aiExamples = document.getElementById('aiExamples');
  if (aiExamples) aiExamples.style.display = 'none';
  
  // Ховаємо AI welcome контейнер
  const aiWelcome = document.getElementById('aiWelcomeContainer');
  if (aiWelcome) aiWelcome.style.display = 'none';
  
  // Додаємо компактне повідомлення про ліміт замість великого блоку
  // Перевіряємо чи вже є повідомлення
  let limitBanner = document.getElementById('chatLimitBanner');
  if (!limitBanner) {
    limitBanner = document.createElement('div');
    limitBanner.id = 'chatLimitBanner';
    limitBanner.className = 'chat-limit-banner';
    
    // Вставляємо після chatThread (в кінець)
    const chatThread = document.getElementById('chatThread');
    if (chatThread && chatThread.parentNode) {
      // Вставляємо після chatThread
      chatThread.parentNode.insertBefore(limitBanner, chatThread.nextSibling);
    }
  }
  
  limitBanner.innerHTML = `
    <div class="limit-banner-content">
      <span class="limit-banner-icon">⏱️</span>
      <div class="limit-banner-text">
        <strong>Досягнуто ліміт запитів</strong>
        <span>Ви використали всі 15 запитів. Спробуйте через <strong id="limitTimer">${minutesLeft} ${minutesLeft === 1 ? 'хв' : 'хв'}</strong> або скористайтесь <a href="#" onclick="activateSimpleSearchFromLimit(); return false;">звичайним пошуком</a></span>
      </div>
    </div>
  `;
  
  // Запускаємо таймер для автоматичної перевірки
  startLimitCheckTimer();
}

// Таймер для автоматичної перевірки ліміту
let limitCheckInterval = null;

function startLimitCheckTimer() {
  // Очищаємо попередній таймер якщо є
  if (limitCheckInterval) {
    clearInterval(limitCheckInterval);
  }
  
  // Перевіряємо кожну хвилину
  limitCheckInterval = setInterval(() => {
    const limitCheck = checkChatSearchLimit();
    
    if (limitCheck.allowed) {
      // Ліміт знято - відновлюємо доступ
      console.log('✅ Ліміт знято, доступ відновлено');
      clearInterval(limitCheckInterval);
      limitCheckInterval = null;
      
      // Якщо ми на сторінці чат-пошуку, приховуємо повідомлення
      if (currentSearchMode === 'chat') {
        hideChatSearchLimitMessage();
        location.reload(); // Перезавантажуємо сторінку для чистого старту
      }
    } else {
      // Оновлюємо таймер
      const timerEl = document.getElementById('limitTimer');
      if (timerEl) {
        const minutes = limitCheck.minutesLeft;
        timerEl.textContent = `${minutes} ${minutes === 1 ? 'хвилину' : minutes < 5 ? 'хвилини' : 'хвилин'}`;
      }
    }
  }, 60000); // Кожну хвилину
}

function hideChatSearchLimitMessage() {
  const limitBanner = document.getElementById('chatLimitBanner');
  if (limitBanner) {
    limitBanner.remove();
  }
  
  // Показуємо пошукову строку
  const searchBox = document.getElementById('chatSearchBox');
  if (searchBox) {
    searchBox.style.display = 'flex';
  }
  
  // Показуємо швидкі кнопки та приклади
  const quickButtons = document.getElementById('quickSearchButtons');
  if (quickButtons) quickButtons.style.display = 'flex';
  
  const aiExamples = document.getElementById('aiExamples');
  if (aiExamples) aiExamples.style.display = 'block';
}

function activateSimpleSearchFromLimit() {
  // Перемикаємось на звичайний пошук
  if (!pages.simple.classList.contains('active')) {
    switchPage('simple');
    hideFooter();
  }
  
  // Фокусуємось на пошуковій строці
  const headerSearchInput = document.getElementById('headerSearchInput');
  if (headerSearchInput) {
    headerSearchInput.focus();
  }
}

// --- Чат-пошук: кожен запит = нова секція ---
let performChatSearchRunning = false;
let activeChatSearchEventSource = null; // Для можливості скасування SSE пошуку

// Функція для скасування поточного пошуку
function cancelChatSearch() {
  if (activeChatSearchEventSource) {
    try {
      activeChatSearchEventSource.close();
      console.log('🛑 Пошук скасовано користувачем');
    } catch(e) {
      console.error('Помилка при закритті EventSource:', e);
    }
    activeChatSearchEventSource = null;
  }
  
  // Скидаємо прапорець активного пошуку
  performChatSearchRunning = false;
  
  // Відновлюємо іконку стрілки
  const btn = document.getElementById('chatSearchButton');
  if (btn) {
    btn.classList.remove('searching');
    btn.innerHTML = '<img src="images/icon_search.png" alt="Пошук" width="20" height="20">';
  }
  
  // Прибираємо індикатор завантаження з останньої секції, якщо є
  const lastSection = document.querySelector('.query-section:last-child');
  if (lastSection) {
    const bodyEl = lastSection.querySelector('.query-body');
    if (bodyEl) {
      // Прибираємо клас завантаження
      bodyEl.classList.remove('loading');
      
      // Знаходимо всі повідомлення асистента, які ще друкуються (мають клас typing)
      const typingMessages = bodyEl.querySelectorAll('.assistant-message.typing');
      typingMessages.forEach(msg => {
        msg.classList.remove('typing');
        // Конвертуємо накопичений текст у HTML (замінюємо \n на <br>)
        if (msg.dataset.rawText) {
          msg.innerHTML = msg.dataset.rawText.replace(/\n/g, '<br>');
          delete msg.dataset.rawText;
        }
      });
      
      // Додаємо повідомлення про скасування
      const cancelMsg = document.createElement('div');
      cancelMsg.className = 'assistant-message';
      cancelMsg.style.color = '#666';
      cancelMsg.style.fontStyle = 'italic';
      cancelMsg.textContent = 'Пошук скасовано';
      bodyEl.appendChild(cancelMsg);
    }
  }
}

async function performChatSearch(directQuery = null){
  // Захист від подвійного виклику
  if (performChatSearchRunning) {
    return;
  }
  
  // Перевіряємо ліміт запитів
  const limitCheck = checkChatSearchLimit();
  if (!limitCheck.allowed) {
    console.warn('⛔ Досягнуто ліміт запитів:', limitCheck);
    showChatSearchLimitMessage(limitCheck.minutesLeft);
    return;
  }
  
  performChatSearchRunning = true;
  
  const query = directQuery || chatSearchInput.value.trim();
  
  if(query.length<2){ 
    performChatSearchRunning = false;
    return alert("Введіть принаймні 2 символи."); 
  }
  
  // Записуємо запит в систему лімітів
  recordChatSearchRequest();
  
  // Встановлюємо режим чат-пошуку
  currentSearchMode = 'chat';
  
  // Ховаємо привітальний блок AI пошуку
  hideAIWelcome();
  
  // Сразу ховаємо швидкі кнопки при пошуку
  const quickButtons = document.getElementById('quickSearchButtons');
  if (quickButtons) {
    quickButtons.style.display = 'none';
  }
  
  // Після першого будь-якого пошуку більше не показуємо вітальну сторінку
  sessionStorage.setItem(WELCOME_SEEN_KEY, '1');
  
  // Гарантуємо що ми на сторінці чат-пошуку
  if (!pages.chat.classList.contains('active')) {
    switchPage('chat');
  }

  // Перевіряємо, чи це перший пошук
  const isFirstSearch = chatStep === 0;
  
  // Переміщуємо пошукову строку вниз при першому пошуку з анімацією
  if (isFirstSearch) {
    const searchBox = document.getElementById('chatSearchBox');
    if (searchBox) {
      // Додаємо клас для анімації переміщення вниз (тільки при першому разі)
      searchBox.classList.remove('chat-search-box--center');
      if (!searchBoxAnimationShown) {
        searchBox.classList.add('chat-search-box--footer');
        searchBox.style.animation = 'slideDownToFooter 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards';
        searchBoxAnimationShown = true;
      } else {
        searchBox.classList.add('chat-search-box--footer-static');
        searchBox.style.animation = 'none';
      }
      
      // Показуємо білий блок під пошуковою строкою
      const footerMask = document.getElementById('footer-mask');
      if (footerMask) {
        footerMask.style.display = 'block';
      }
      
      // Додаємо додатковий ефект для плавного переходу
      searchBox.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
      
      // Строка залишається видимою на екрані при прокручуванні
    }
    
  }
  
  // Скидаємо контекст діалогу для нового пошуку
  chatDialogContext = null;
  
  chatSearchInput.value = '';
  
  // Змінюємо іконку кнопки на квадратик (кнопка зупинки)
  const btn = document.getElementById('chatSearchButton');
  if (btn) {
    btn.classList.add('searching');
    btn.classList.add('visible'); // Показуємо кнопку під час пошуку
    btn.innerHTML = '<div class="stop-icon"></div>';
  }
  
  try{
    // Запитати конфіг і визначити, чи вмикати стрімінг
    const cfg = await fetch('/config', { cache: 'no-store' }).then(r=>r.ok?r.json():({})).catch(()=>({}));
    if (typeof cfg.feature_chat_sse === 'boolean') {
      FEATURE_CHAT_STREAMING = cfg.feature_chat_sse;
    }
  }catch(_){ /* ignore */ }

  if (FEATURE_CHAT_STREAMING) {
    runChatRoundStreaming({ type: 'text', value: query });
  } else {
    runChatRound({ type: 'text', value: query });
  }
  
  // Скидаємо прапорець після запуску пошуку
  setTimeout(() => {
    performChatSearchRunning = false;
  }, 2000);
}

async function runChatRound(input){
  // Переміщуємо привітальне повідомлення вгору після першого пошуку
  moveWelcomeMessageUp();
  
  const isCategoryFilter = input?.type === 'category';
  
  let section, sectionId, bodyEl;
  
  if (isCategoryFilter) {
    // При фільтрації категорій - оновлюємо секцію, з якої клікнули (sectionId)
    const targetStep = Number(input.sectionId);
    const targetSelector = isFinite(targetStep) && targetStep > 0 
      ? `.query-section[data-step="${targetStep}"]`
      : '.query-section:last-child';
    const targetSection = document.querySelector(targetSelector);
    if (targetSection) {
      section = targetSection;
      sectionId = parseInt(section.dataset.step) || chatStep;
      bodyEl = section.querySelector('.query-body');
      // Лише додаємо клас завантаження, не очищаємо контент з текстом асистента
      bodyEl.classList.add('loading');
    } else {
      // Якщо немає секції - створюємо нову
      sectionId = ++chatStep;
      const userText = `Обрана категорія: ${input.valueLabel || input.value}`;
      section = renderPendingSection(sectionId, userText);
      bodyEl = section.querySelector('.query-body');
    }

    // КЛІЄНТСЬКА ФІЛЬТРАЦІЯ БЕЗ ЗАПИТУ ДО БЕКЕНДА (по секції)
    try {
      // Читаємо контекст секції з DOM, якщо є
      let sectionCtx = null;
      try {
        const ctxEl = section.querySelector('script[type="application/json"][data-section-context]');
        sectionCtx = ctxEl ? JSON.parse(ctxEl.textContent || '{}') : null;
      } catch(_) { sectionCtx = null; }

      const allProducts = Array.isArray(sectionCtx?.all_products) ? sectionCtx.all_products : (Array.isArray(chatDialogContext?.all_products) ? chatDialogContext.all_products : []);
      const buckets = sectionCtx?.category_buckets || chatDialogContext?.category_buckets || {};
      const currentFilter = (typeof sectionCtx?.current_filter !== 'undefined') ? sectionCtx.current_filter : (chatDialogContext?.current_filter || null);
      const recoIdsFromCtx = Array.isArray(sectionCtx?.reco_ids) ? sectionCtx.reco_ids : (Array.isArray(chatDialogContext?.reco_ids) ? chatDialogContext.reco_ids : []);
      const actions = sectionCtx?.actions || chatDialogContext?.actions || [];

      // Обчислюємо код категорії (допускаємо як код, так і label)
      const resolved = resolveCategoryCodeAndLabel(input?.value || input?.valueLabel);
      const selectedCode = resolved.code;

      // Тогл фільтра
      const newFilter = (selectedCode && selectedCode === currentFilter) ? null : selectedCode;

      // Відбір товарів
      let filtered = allProducts;
      if (newFilter) {
        // Спочатку шукаємо по label (наприклад "⭐ Рекомендовано для вас")
        const bucketItems = buckets[input?.value] || buckets[input?.valueLabel] || buckets[newFilter];
        
        if (Array.isArray(bucketItems) && bucketItems.length > 0) {
          // bucketItems містить ID товарів (strings), а не об'єкти
          const idSet = new Set(bucketItems);
          filtered = allProducts.filter(p => idSet.has(p.id));
        } else {
          // Fallback по ключових словах з CATEGORY_SCHEMA
          const kws = CATEGORY_SCHEMA[newFilter]?.keywords || [];
          if (kws.length > 0) {
            const hay = (p) => `${p?.title_ua || ''} ${p?.description_ua || ''}`.toLowerCase();
            filtered = allProducts.filter(p => kws.some(kw => hay(p).includes(kw)));
          } else {
            filtered = allProducts; // Показуємо все якщо немає фільтрів
          }
        }
      }

      // Оновлюємо контекст секції в DOM і оновлюємо карусель
      const ctxEl = section.querySelector('script[type="application/json"][data-section-context]') || (function(){ const el=document.createElement('script'); el.type='application/json'; el.setAttribute('data-section-context',''); section.appendChild(el); return el; })();
      const newCtx = JSON.stringify({
        available_categories: (sectionCtx?.available_categories || chatDialogContext?.available_categories || []),
        all_products: allProducts,
        category_buckets: buckets,
        current_filter: newFilter,
        reco_ids: recoIdsFromCtx
      });
      ctxEl.textContent = newCtx;
      
      updateCarouselInSection(section, { products: filtered });
      return; // важливо: не робимо мережевий запит і не створюємо нову секцію
    } catch (e) {
      console.error('❌ Клієнтська фільтрація не вдалася, fallback на бекенд:', e);
      // Якщо щось пішло не так, падаємо у стандартний шлях з бекендом нижче
    }
  } else {
    // Для нового пошуку - створюємо нову секцію
    sectionId = ++chatStep;
    const userText = input?.type === 'category' ? `Обрана категорія: ${input.valueLabel || input.value}` : input?.value || '';
    section = renderPendingSection(sectionId, userText);
    bodyEl = section.querySelector('.query-body');
    
    // НЕ показуємо fallback повідомлення (для категорій це швидкий запит)
  }

  try{
    // 1) Чат-пошук з діалогом та категоріями (BM25 + GPT на бекенді)
    const chatData = await fetchChatAnalysisPayload({
      input,
      dialog_context: chatDialogContext,
    });
    chatDialogContext = chatData?.dialog_context || null;
    
    // Додаємо запит до історії для контекстного розуміння
    if (!isCategoryFilter && input?.value) {
      addToSearchHistory(input.value);
    }
    
    const advice = chatData?.assistant_message || '';
    const products = Array.isArray(chatData?.results) ? chatData.results : [];
    const recommendations = Array.isArray(chatData?.recommendations) ? chatData.recommendations : [];
    const actions = Array.isArray(chatData?.actions) ? chatData.actions : null;
    const needsInput = !!chatData?.needs_user_input;
    // Лог назв товарів (чат-пошук)
    logProductTitles('chat-search', products);
    
    // Невелика затримка для плавності
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // 2) Рендер: повідомлення асистента зліва + (опційно) кнопки категорій + карусель
    if (isCategoryFilter) {
      // При фільтрації - оновлюємо тільки карусель, зберігаючи повідомлення
      updateCarouselInSection(section, { products, recommendations });
    } else {
      // Для нового пошуку - рендеримо всю секцію; показуємо ВСІ товари (спершу рекомендовані)
      finalizeSection(section, { advice, products, recommendations, actions, needsInput });
      // Зберігаємо контекст секції в DOM для незалежної фільтрації
      try {
        const ctxEl = document.createElement('script');
        ctxEl.type = 'application/json';
        ctxEl.setAttribute('data-section-context','');
        
        // Витягуємо категорії з actions
        const categoriesFromActions = Array.isArray(actions) 
          ? actions
              .filter(a => a?.type === 'button' && a?.action === 'select_category')
              .map(a => a.value)
          : [];
        
        const ctx = {
          available_categories: categoriesFromActions.length > 0 ? categoriesFromActions : (chatDialogContext?.available_categories || []),
          all_products: Array.isArray(products) ? products : [],
          category_buckets: (chatDialogContext?.category_buckets || {}),
          current_filter: null,
          reco_ids: Array.isArray(recommendations) ? recommendations.map(r => r.product_id) : [],
          actions: actions  // Зберігаємо actions з special прапорцями
        };
        ctxEl.textContent = JSON.stringify(ctx);
        section.appendChild(ctxEl);
      } catch(_) {}
    }
    updateSelectedCards();
    
    // 4) Показуємо футер після завантаження товарів (тільки для першого пошуку)
    if (sectionId === 1) {
      showFooter();
    }
    
    // Відновлюємо іконку кнопки після успішного завершення
    const btn = document.getElementById('chatSearchButton');
    if (btn) {
      btn.classList.remove('searching');
      btn.classList.remove('visible');
      btn.innerHTML = '<img src="images/icon_search.png" alt="Пошук" width="20" height="20">';
    }

  } catch(error) {
    console.error('❌ Помилка чат-пошуку:', error);
    setSectionError(section, error.message);
    
    // Відновлюємо іконку кнопки при помилці
    const btn = document.getElementById('chatSearchButton');
    if (btn) {
      btn.classList.remove('searching');
      btn.classList.remove('visible');
      btn.innerHTML = '<img src="images/icon_search.png" alt="Пошук" width="20" height="20">';
    }
  }
}

// Стрімінговий варіант
async function runChatRoundStreaming(input){
  // Переміщуємо привітальне повідомлення вгору після першого пошуку
  moveWelcomeMessageUp();
  
  const isCategoryFilter = input?.type === 'category';
  if (isCategoryFilter) {
    // Для категорій поки що лишаємо існуючий POST без SSE
    return runChatRound(input);
  }

  let section, sectionId, bodyEl;
  {
    chatStep += 1;
    sectionId = chatStep;
    section = renderPendingSection(sectionId, input?.value || '');
    bodyEl = section.querySelector('.query-body');
    
    // НЕ показуємо повідомлення одразу - чекаємо на події від сервера
  }

  try{
    const sessionId = `session_${Date.now()}`;
    const params = new URLSearchParams({ query: input.value, session_id: sessionId, k: String(100) });
    
    // Передаємо search_history окремим параметром (НЕ в dialog_context!)
    const historyJson = JSON.stringify(getSearchHistory());
    const historyB64 = btoa(unescape(encodeURIComponent(historyJson)));
    params.append('search_history_b64', historyB64);
    
    // Додаємо dialog_context якщо він є (БЕЗ search_history - вона передається окремо)
    if (chatDialogContext) {
      try {
        const contextJson = JSON.stringify(chatDialogContext);
        const contextB64 = btoa(unescape(encodeURIComponent(contextJson)));
        params.append('dialog_context_b64', contextB64);
        console.log('📤 Передаємо dialog_context в SSE:', chatDialogContext);
        
        // Логуємо критично важливе поле для діагностики
        if (chatDialogContext.clarification_asked) {
          console.warn('⚠️ УВАГА: clarification_asked=true! GPT ПОВИНЕН шукати товари, а НЕ питати знову!');
          console.warn('⚠️ Категорії які були запропоновані:', chatDialogContext.categories_suggested);
        }
      } catch(e) {
        console.warn('Помилка при кодуванні dialog_context:', e);
      }
    }
    
    // Функція для відновлення іконки кнопки після завершення пошуку
    function restoreSearchButton() {
      activeChatSearchEventSource = null;
      const btn = document.getElementById('chatSearchButton');
      if (btn) {
        btn.classList.remove('searching');
        btn.classList.remove('visible');
        btn.innerHTML = '<img src="images/icon_search.png" alt="Пошук" width="20" height="20">';
      }
    }
    
    // Початок SSE пошуку
    const es = new EventSource(`${CHAT_SEARCH_SSE_URL}?${params.toString()}`);
    activeChatSearchEventSource = es; // Зберігаємо для можливості скасування
    let finalPayload = null;

    // Новий обробник для статусних повідомлень
    es.addEventListener('status', (ev)=>{
      try{
        const data = JSON.parse(ev.data);
        const message = data.message || '';
        const type = data.type || '';
        
        // Прибираємо попереднє повідомлення статусу якщо є
        const oldStatus = bodyEl.querySelector('.status-message');
        if (oldStatus) {
          const parentDiv = oldStatus.closest('.assistant-message');
          if (parentDiv) parentDiv.remove();
        }
        
        // Прибираємо попередній кружечок якщо є
        const oldLoader = bodyEl.querySelector('.dot-loader');
        if (oldLoader) {
          const parentDiv = oldLoader.closest('.assistant-message');
          if (parentDiv) parentDiv.remove();
        }
        
        // Прибираємо попередній shimmer текст якщо є
        const oldShimmer = bodyEl.querySelector('.shimmer-text');
        if (oldShimmer) {
          const parentDiv = oldShimmer.closest('.assistant-message');
          if (parentDiv) parentDiv.remove();
        }
        
        // Показуємо новий анімований кружечок під час завантаження
        if (message) {
          const statusDiv = document.createElement('div');
          statusDiv.className = 'assistant-message';
          statusDiv.style.background = 'transparent';
          statusDiv.style.animation = 'none';
          // Визначаємо текст на основі типу повідомлення
          let statusText = 'Думаю';
          if (type === 'searching') {
            statusText = 'Шукаю товари';
          } else if (type === 'thinking') {
            statusText = 'Думаю';
          }
          statusDiv.innerHTML = `<!--<div class="dot-loader"></div>--><span class="loader-text shimmer-text">${statusText}</span>`;
          bodyEl.appendChild(statusDiv);
        }
      }catch(e){ console.warn('Status event error:', e); }
    });

    es.addEventListener('analysis', (ev)=>{
      // Подію отримано, але не виводимо етапи
    });

    es.addEventListener('candidates', (ev)=>{
      // Подію отримано, але не виводимо етапи
    });

    es.addEventListener('categories', (ev)=>{
      // Подію отримано, але не виводимо етапи
    });

    es.addEventListener('recommendations', (ev)=>{
      // Подію отримано, але не виводимо етапи
    });

    // Стрім «набору» відповіді асистента (бекенд вже відправляє посимвольно)
    let assistantMsg = null;
    let assistantTypingComplete = false;
    
    es.addEventListener('assistant_start', (ev)=>{
      // Прибираємо повідомлення "Шукаю товари" та статусні повідомлення
      const searchingMessage = bodyEl.querySelector('.searching-message');
      if (searchingMessage) {
        const parentDiv = searchingMessage.closest('.assistant-message');
        if (parentDiv) {
          parentDiv.remove();
        } else {
          searchingMessage.remove();
        }
      }
      
      // Прибираємо статусні повідомлення ("Думаю...", "Шукаю товари...")
      const statusMessage = bodyEl.querySelector('.status-message');
      if (statusMessage) {
        const parentDiv = statusMessage.closest('.assistant-message');
        if (parentDiv) {
          parentDiv.remove();
        } else {
          statusMessage.remove();
        }
      }
      
      // Прибираємо анімований кружечок
      const dotLoader = bodyEl.querySelector('.dot-loader');
      if (dotLoader) {
        const parentDiv = dotLoader.closest('.assistant-message');
        if (parentDiv) {
          parentDiv.remove();
        } else {
          dotLoader.remove();
        }
      }
      
      // Прибираємо shimmer текст ("Думаю", "Шукаю")
      const shimmerText = bodyEl.querySelector('.shimmer-text');
      if (shimmerText) {
        const parentDiv = shimmerText.closest('.assistant-message');
        if (parentDiv) {
          parentDiv.remove();
        } else {
          shimmerText.remove();
        }
      }
      
      // Створюємо нове повідомлення асистента
      assistantMsg = document.createElement('div');
      assistantMsg.className = 'assistant-message typing';
      assistantMsg.textContent = '';
      assistantMsg.dataset.rawText = '';
      bodyEl.appendChild(assistantMsg);
      
      // Клас loading залишається активним під час друку тексту GPT
    });
    
    es.addEventListener('assistant_delta', (ev)=>{
      try{
        const d = JSON.parse(ev.data);
        // Просто додаємо символ (бекенд вже відправляє з затримкою)
        if (assistantMsg && d.text) {
          // Накопичуємо текст і одразу конвертуємо \n в <br> для правильного форматування під час друку
          if (!assistantMsg.dataset.rawText) assistantMsg.dataset.rawText = '';
          assistantMsg.dataset.rawText += d.text;
          // Використовуємо innerHTML з конвертацією \n в <br> щоб нові рядки відображались під час streaming
          assistantMsg.innerHTML = assistantMsg.dataset.rawText.replace(/\n/g, '<br>');
        }
      }catch(_){ }
    });
    
    es.addEventListener('assistant_end', (ev)=>{
      if (assistantMsg) {
        assistantMsg.classList.remove('typing');
        // Конвертація \n в <br> вже виконана в assistant_delta, просто очищаємо dataset
        if (assistantMsg.dataset.rawText) {
          delete assistantMsg.dataset.rawText;
        }
      }
      assistantTypingComplete = true;
      
      // Якщо payload вже прийшов, рендеримо карусель
      if (finalPayload) {
        renderCarouselAfterAssistant();
      }
    });

    es.addEventListener('final', (ev)=>{
      try{
        finalPayload = JSON.parse(ev.data);
        es.close();
        restoreSearchButton(); // Відновлюємо іконку після завершення пошуку
        
        // Додаємо запит до історії для контекстного розуміння наступних запитів
        if (input?.value) {
          addToSearchHistory(input.value);
          console.log('📜 Додано до історії:', input.value, '| Всього:', searchHistory.length);
        }
        
        // Рендеримо категорії та карусель ТІЛЬКИ після завершення друку тексту
        if (assistantTypingComplete) {
          renderCarouselAfterAssistant();
        }
      }catch(e){ 
        console.error('SSE final event error:', e); 
        es.close(); 
        restoreSearchButton(); // Відновлюємо іконку навіть при помилці
      }
    });
    
    // Функція для рендерингу каруселі після завершення тексту асистента
    function renderCarouselAfterAssistant() {
      if (!finalPayload) return;
      
      // Прибираємо клас loading перед показом товарів
      bodyEl.classList.remove('loading');
      
      // Додаємо невелику затримку перед показом товарів для плавності
      setTimeout(() => {
        // Рендеримо категорії та карусель (текст асистента вже є через SSE)
        finalizeSectionWithoutTextTyping(bodyEl, {
          products: finalPayload.results || [],
          recommendations: finalPayload.recommendations || [],
          actions: finalPayload.actions || null
        });
        
        // Оновити контекст
        chatDialogContext = finalPayload.dialog_context || null;
        console.log('📥 Оновлено chatDialogContext:', chatDialogContext);
        
        // Логуємо clarification_asked якщо є
        if (chatDialogContext?.clarification_asked) {
          console.warn('⚠️ chatDialogContext містить clarification_asked=true');
          console.warn('⚠️ Наступний запит ПОВИНЕН призвести до пошуку товарів!');
        }
        
        // Зберегти контекст секції для фільтрації
        try {
          const ctxEl = document.createElement('script');
          ctxEl.type = 'application/json';
          ctxEl.setAttribute('data-section-context','');
          
          // Витягуємо категорії з actions
          const categoriesFromActions = Array.isArray(finalPayload.actions) 
            ? finalPayload.actions
                .filter(a => a?.type === 'button' && a?.action === 'select_category')
                .map(a => a.value)
            : [];
          
          const ctx = {
            available_categories: categoriesFromActions.length > 0 ? categoriesFromActions : (chatDialogContext?.available_categories || []),
            all_products: finalPayload.results || [],
            category_buckets: (chatDialogContext?.category_buckets || {}),
            current_filter: null,
            reco_ids: (finalPayload.recommendations || []).map(r => r.product_id),
            actions: finalPayload.actions  // Зберігаємо actions з special прапорцями
          };
          ctxEl.textContent = JSON.stringify(ctx);
          section.appendChild(ctxEl);
        } catch(_) {}
        
        updateSelectedCards();
        if (sectionId === 1) showFooter();
      }, 300); // Затримка 300мс після завершення друку тексту
    }

    let fallbackCalled = false;
    
    es.onerror = () => { 
      try{ es.close(); }catch(_){ } 
      restoreSearchButton(); // Відновлюємо іконку при помилці
      
      // Викликаємо fallback тільки один раз
      if (!fallbackCalled) {
        fallbackCalled = true;
        // Видаляємо секцію, яку створили для SSE
        if (section && section.parentNode) {
          section.parentNode.removeChild(section);
        }
        // Зменшуємо chatStep назад, бо ми видалили секцію
        chatStep--;
        // Викликаємо звичайний runChatRound, який створить нову секцію
        runChatRound(input).catch(()=>{});
      }
    };
  }catch(e){
    console.error('SSE error:', e);
    // Видаляємо секцію, якщо вона вже створена
    if (section && section.parentNode) {
      section.parentNode.removeChild(section);
    }
    chatStep--;
    return runChatRound(input);
  }
}

// Оновлюємо тільки карусель в існуючій секції (для фільтрації категорій)
function updateCarouselInSection(section, { products, recommendations = [] }) {
  const body = section.querySelector('.query-body');
  body.classList.remove('loading');
  
  // Зберігаємо кнопки категорій (якщо є)
  const existingCategoriesWrap = body.querySelector('.categories-wrap');
  
  // Знаходимо існуючу карусель або створюємо нову
  let existingCarousel = body.querySelector('.carousel-container');
  if (!existingCarousel) {
    // Створюємо контейнер для каруселі
    existingCarousel = document.createElement('div');
    existingCarousel.className = 'carousel-container';
    
    // Вставляємо після категорій (якщо є) або в кінець
    if (existingCategoriesWrap) {
      existingCategoriesWrap.after(existingCarousel);
    } else {
      body.appendChild(existingCarousel);
    }
  }
  
  // Прибираємо старі елементи навігації/підказки, щоб не дублювались
  existingCarousel.querySelectorAll('.carousel-nav-btn, .carousel-hint').forEach(el => el.remove());

  // Знаходимо або створюємо карусель
  let carousel = existingCarousel.querySelector('.products-carousel');
  if (!carousel) {
    carousel = document.createElement('div');
    carousel.className = 'products-carousel compact';
    existingCarousel.appendChild(carousel);
    
    // Додаємо drag scroll функціональність
    addDragScrollToCarousel(carousel);
  }
  
  // Об'єднати: спочатку рекомендовані, потім решта
  let recoIds = Array.isArray(recommendations) ? recommendations.map(r => r.product_id) : [];
  if (!recoIds.length) {
    try {
      const ctxEl = section.querySelector('script[type="application/json"][data-section-context]');
      const sectionCtx = ctxEl ? JSON.parse(ctxEl.textContent || '{}') : null;
      if (Array.isArray(sectionCtx?.reco_ids)) {
        recoIds = sectionCtx.reco_ids;
      }
    } catch(_) {}
  }
  const mergedProducts = (() => {
    if (!Array.isArray(products) || products.length === 0) return [];
    const byId = new Map(products.map(p => [p.id, p]));
    const recommended = recoIds.map(id => byId.get(id)).filter(Boolean);
    const remaining = products.filter(p => !recoIds.includes(p.id));
    return [...recommended, ...remaining];
  })();
  
  // Визначаємо sortedProducts для використання поза блоками
  const sortedProducts = mergedProducts;

  if (mergedProducts.length === 0) {
    carousel.innerHTML = `<div class="result-placeholder"><p>Нічого не знайдено.</p></div>`;
  } else {
    // Показуємо ВСІ товари: рекомендовані спочатку

    carousel.innerHTML = '';

    sortedProducts.forEach((p) => {
      const card = document.createElement('div');
      card.className = 'product-card';
      card.dataset.id = p.id;
      card.dataset.uuid = p.uuid;

      // Клік по картці — як у основній каруселі
      card.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (card.classList.contains('loading')) return;
        await toggleCartItem(p);
      };

      const isRecommended = recoIds.includes(p.id);
      const recommendationBadge = isRecommended ? '<div class="recommendation-badge">⭐ Рекомендовано</div>' : '';

      card.innerHTML = `
        ${recommendationBadge}
        <div class="product-image-container">
          <div class="image-placeholder">Завантаження...</div>
        </div>
        <div class="product-details">
          <h3>${escapeHTML(p.title_ua||'Без назви')}</h3>
          <p>${escapeHTML((p.description_ua||'').slice(0,100))}...</p>
          <div class="product-pricing-info">
            <div class="rating-placeholder"></div>
            <div class="price-placeholder">Завантаження ціни...</div>
          </div>
        </div>`;

      carousel.appendChild(card);

      // Стан завантаження як у основній каруселі
      card.classList.add('loading');

      const priceElement = card.querySelector('.price-placeholder');
      const ratingElement = card.querySelector('.rating-placeholder');
      const imageElement = card.querySelector('.product-image-container');

      // Додаємо good_code як data-атрибут для lazy loading
      imageElement.dataset.goodCode = p.good_code;
      
      // Ініціалізуємо observer якщо ще не ініційований
      initImageObserver();
      
      // Додаємо контейнер зображення до observer для lazy loading
      imageObserver.observe(imageElement);

      Promise.all([
        loadProductPrice(priceElement, p.good_code, p),
        loadProductRating(ratingElement, p.good_code, p)
      ]).finally(() => {
        card.classList.remove('loading');
      });
    });
  }
  
  // Додаємо кнопки навігації та індикатори сторінок
  const prevBtn = document.createElement('button');
  prevBtn.className = 'carousel-nav-btn prev';
  prevBtn.innerHTML = '‹';
  prevBtn.onclick = () => scrollCarousel(carousel, 'prev');

  const nextBtn = document.createElement('button');
  nextBtn.className = 'carousel-nav-btn next';
  nextBtn.innerHTML = '›';
  nextBtn.onclick = () => scrollCarousel(carousel, 'next');

  // hint removed

  existingCarousel.appendChild(prevBtn);
  existingCarousel.appendChild(nextBtn);

  carousel.addEventListener('scroll', () => updateCarouselState(carousel, prevBtn, nextBtn));
  // після рендеру повертаємося на початок каруселі
  try { carousel.scrollTo({ left: 0, behavior: 'auto' }); } catch(_) { carousel.scrollLeft = 0; }
  
  // Оновлюємо кнопки категорій ПЕРЕД додаванням кнопки розгортання
  updateCategoryButtons(body);
  
  // Додаємо кнопку розгортання каруселі ПОСЛЯ індикаторів (тільки якщо її ще немає)
  if (!existingCarousel.querySelector('.carousel-expand-container')) {
    const expandContainer = createExpandToggleButton(existingCarousel, sortedProducts.length);
    existingCarousel.appendChild(expandContainer);
  } else {
    // Оновлюємо кількість товарів в існуючій кнопці
    const existingBtn = existingCarousel.querySelector('.expand-toggle-btn');
    if (existingBtn) {
      existingBtn.innerHTML = `Показати всі товари (${sortedProducts.length}) <span class="expand-icon">↓</span>`;
    }
  }
  
  // Відновлюємо стан каруселі з sessionStorage
  restoreCarouselState(existingCarousel);

  // Оновлюємо видимість кнопки "Вгору"
  if (typeof updateBackToTopVisibility === 'function') {
    try { updateBackToTopVisibility(); } catch(_){}
  }
}

// Оновлюємо кнопки категорій в існуючій секції
function resolveCategoryCodeAndLabel(value) {
  const raw = String(value || '').trim();
  if (CATEGORY_SCHEMA[raw]) {
    return { code: raw, label: CATEGORY_SCHEMA[raw].label || raw };
  }
  // try match by label
  for (const [code, data] of Object.entries(CATEGORY_SCHEMA)) {
    if ((data?.label || '').toLowerCase() === raw.toLowerCase()) {
      return { code, label: data.label || code };
    }
  }
  return { code: raw, label: raw };
}

function updateCategoryButtons(body) {
  console.log('🔄 updateCategoryButtons: викликано');
  
  // Знаходимо існуючий контейнер кнопок або створюємо новий
  let existingButtons = body.querySelector('.categories-wrap');
  if (!existingButtons) {
    // Створюємо контейнер для кнопок
    existingButtons = document.createElement('div');
    existingButtons.className = 'categories-wrap';
    existingButtons.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 6px 0;';
    
    // Вставляємо перед каруселлю
    const carouselContainer = body.querySelector('.carousel-container');
    if (carouselContainer) {
      body.insertBefore(existingButtons, carouselContainer);
    } else {
      body.appendChild(existingButtons);
    }
    console.log('✅ Створено новий контейнер категорій');
  } else {
    console.log('♻️ Використовую існуючий контейнер категорій');
  }
  
  // Очищаємо існуючі кнопки
  existingButtons.innerHTML = '';
  
  // Додаємо заголовок
  existingButtons.innerHTML = '<div style="font-size:12px;color:#666;margin-right:8px;align-self:center;">Фільтри:</div>';
  
  // Додаємо кнопки категорій
  // Категорії беруться з контексту СЕКЦІЇ, якщо він збережений у DOM
  const section = body.closest('.query-section');
  const sectionContextEl = section ? section.querySelector('script[type="application/json"][data-section-context]') : null;
  let sectionCtx = null;
  try { sectionCtx = sectionContextEl ? JSON.parse(sectionContextEl.textContent || '{}') : null; } catch(_) { sectionCtx = null; }

  console.log('🔍 sectionCtx:', sectionCtx);
  console.log('🔍 chatDialogContext:', chatDialogContext);

  const available = (sectionCtx && Array.isArray(sectionCtx.available_categories)) ? sectionCtx.available_categories : (chatDialogContext && Array.isArray(chatDialogContext.available_categories) ? chatDialogContext.available_categories : []);
  const currentFilter = sectionCtx && typeof sectionCtx.current_filter !== 'undefined' ? sectionCtx.current_filter : chatDialogContext?.current_filter;
  const actions = (sectionCtx && Array.isArray(sectionCtx.actions)) ? sectionCtx.actions : (chatDialogContext && Array.isArray(chatDialogContext.actions) ? chatDialogContext.actions : []);

  console.log('📋 available categories:', available);
  console.log('🎯 current filter:', currentFilter);
  console.log('⚡ actions:', actions);

  if (available && available.length > 0) {
    available.forEach(v => {
      const { code, label } = resolveCategoryCodeAndLabel(v);
      const isActive = currentFilter === code;
      
      // Знаходимо відповідну action щоб перевірити special прапорець
      const action = actions.find(a => a?.value === v || a?.label === v);
      const isRecommended = action?.special === 'recommended';
      
      const btn = document.createElement('button');
      btn.textContent = label;
      
      // Особливий стиль для категорії "Рекомендовано"
      if (isRecommended && !isActive) {
        btn.style.cssText = 'background:linear-gradient(135deg, #ffd24d 0%, #ffb84d 100%);border:none;border-radius:18px;padding:8px 16px;cursor:pointer;font-size:13px;font-weight:600 !important;color:#000;box-shadow:0 2px 8px rgba(255,210,77,0.4);user-select:none;-webkit-user-select:none;transition:all 0.2s ease;';
        btn.onmouseenter = () => btn.style.transform = 'translateY(-1px)';
        btn.onmouseleave = () => btn.style.transform = 'translateY(0)';
      } else if (isActive) {
        btn.style.cssText = 'background:#ffd24d;border:none;border-radius:18px;padding:8px 12px;cursor:pointer;font-size:13px;font-weight:400 !important;user-select:none;-webkit-user-select:none;';
      } else {
        btn.style.cssText = 'background:#fff;border:1px solid #e0e0e0;border-radius:18px;padding:8px 12px;cursor:pointer;font-size:13px;font-weight:400 !important;user-select:none;-webkit-user-select:none;';
      }
      
      btn.onclick = () => runChatRound({ type: 'category', value: code, valueLabel: label, sectionId: section ? Number(section.dataset.step) : undefined });
      existingButtons.appendChild(btn);
    });
    existingButtons.style.display = 'flex';
  } else {
    // Ховаємо кнопки, якщо категорій немає
    existingButtons.style.display = 'none';
    console.warn('⚠️ Немає доступних категорій для відображення');
  }
}

// Надійний запит до GPT-підказок із повтором
async function fetchChatAnalysisPayload({ input, dialog_context = null, retries = 2 } = {}){
  const isCategory = input?.type === 'category';
  const requestData = {
    query: isCategory ? (dialog_context?.original_query || '') : (input?.value || ''),
    search_history: getSearchHistory(),
    session_id: `session_${Date.now()}`,
    k: 100,
    dialog_context: dialog_context || undefined,
    selected_category: isCategory ? input.value : undefined,
  };
  
  // Початок пошуку
  
  let lastError;
  for(let attempt=0; attempt<=retries; attempt++){
    try{
      const t0 = performance.now();
      const res = await fetch(CHAT_SEARCH_API_URL, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(requestData)
      });
      if(!res.ok){
        const msg = await res.text().catch(()=>`status ${res.status}`);
        throw new Error(`HTTP ${res.status}: ${msg}`);
      }
      const data = await res.json();
      const duration = Math.round(performance.now() - t0);
      
      // Логування результатів
      console.log(`✅ Пошук завершено за ${duration}ms`);
      console.log(`📊 Метод: 🔀 Hybrid Search (Semantic + BM25)`);
      
      // Детальное логирование анализа GPT
      if (data.query_analysis) {
        console.log('🧠 GPT АНАЛІЗ ЗАПИТУ:');
        console.log(`   📝 Оригінальний запит: "${data.query_analysis.original_query}"`);
        console.log(`   💭 Розширений запит: "${data.query_analysis.expanded_query}"`);
        console.log(`   🎯 Намір: ${data.query_analysis.intent_description || 'не визначено'}`);
        console.log(`   🔑 Ключові слова: [${data.query_analysis.keywords?.join(', ') || 'немає'}]`);
        
        if (data.query_analysis.semantic_subqueries && data.query_analysis.semantic_subqueries.length > 0) {
          console.log(`   🔍 СЕМАНТИЧНІ ПІДЗАПИТИ (${data.query_analysis.semantic_subqueries.length}):`);
          data.query_analysis.semantic_subqueries.forEach((subquery, index) => {
            console.log(`      ${index + 1}. "${subquery}"`);
          });
        } else {
          console.log('   ⚠️ Семантичні підзапити не знайдені');
        }
      }
      
      if (data.stage_timings_ms) {
        console.log('⏱️ Таймінги етапів:');
        console.table(data.stage_timings_ms);
      }
      console.log(`📦 Знайдено товарів: ${data.results?.length || 0}`);
      console.log(`⭐ Рекомендацій GPT: ${data.recommendations?.length || 0}`);
      
      return data;
    }catch(err){
      lastError = err;
      console.warn(`⚠️ Спроба ${attempt + 1}/${retries + 1} не вдалася:`, err.message);
      // Невелика експоненційна затримка
      const backoff = 200 * Math.pow(2, attempt);
      await new Promise(r=>setTimeout(r, backoff));
    }
  }
  throw lastError || new Error('Unknown GPT recommendations error');
}


// --- Показ повідомлення "Шукаю товари" ---
function showSearchingMessage(bodyEl) {
  // Створюємо повідомлення від GPT в стилі чат-бабла з анімованим кружечком
  const searchingDiv = document.createElement('div');
  searchingDiv.className = 'assistant-message';
  searchingDiv.style.background = 'transparent';
  searchingDiv.style.animation = 'none';
  searchingDiv.innerHTML = `
    <!--<div class="dot-loader"></div>--><span class="loader-text shimmer-text">Шукаю</span>
  `;
  bodyEl.appendChild(searchingDiv);
}

// --- Рендер секції (підготовка / фіналізація / помилка) ---
function renderPendingSection(step, userText){
  const wrap = document.createElement('div');
  wrap.className = 'query-section';
  wrap.dataset.step = step;
  wrap.innerHTML = `
    <div class="query-header">
      <span class="query-pill" title="Ваш запит" style="margin-left:auto;">${escapeHTML(userText)}</span>
    </div>
    <div class="query-body" id="qbody-${step}">
    </div>
  `;
  chatThread.appendChild(wrap);

  // автоскролл к месту, где вскоре будут товари (без второго скролла после загрузки)
  const bodyEl = wrap.querySelector('.query-body');
  bodyEl.classList.add('loading');

  if (FEATURE_CHAT_AUTOSCROLL) {
    setTimeout(() => {
      scrollToFutureSpot(wrap, { first: step === 1 });
    }, 30);
  }

  return wrap;
}
function scrollToFutureSpot(sectionEl, opts = {}) {
  // Прокручуємо так, щоб верх секції став одразу під хедером
  const header = document.querySelector('.tda-header');
  const headerOffset = (header && header.offsetHeight) ? header.offsetHeight : 0;
  const safetyMargin = 12; // невеликий відступ від хедера

  const sectionTop = sectionEl.getBoundingClientRect().top + window.pageYOffset;
  let targetY = sectionTop - headerOffset - safetyMargin;

  // Клап на межі документа, щоб не "перестрибувати"
  const maxY = Math.max(0, (document.documentElement.scrollHeight || document.body.scrollHeight) - window.innerHeight);
  if (targetY > maxY) targetY = maxY;
  if (targetY < 0) targetY = 0;

  window.scrollTo({ top: targetY, behavior: 'smooth' });
}

async function finalizeSection(section,{advice,products,recommendations = [], actions = null, needsInput = false}){
  const body = section.querySelector('.query-body');
  body.classList.remove('loading');
  
  // Прибираємо повідомлення "Шукаю товари" коли система знайшла товари
  const searchingMessage = body.querySelector('.searching-message');
  if (searchingMessage) {
    searchingMessage.remove();
  }
  
  // Прибираємо анімований кружечок
  const dotLoader = body.querySelector('.dot-loader');
  if (dotLoader) {
    const parentDiv = dotLoader.closest('.assistant-message');
    if (parentDiv) {
      parentDiv.remove();
    } else {
      dotLoader.remove();
    }
  }
  
  // Прибираємо shimmer текст ("Думаю", "Шукаю")
  const shimmerText = body.querySelector('.shimmer-text');
  if (shimmerText) {
    const parentDiv = shimmerText.closest('.assistant-message');
    if (parentDiv) {
      parentDiv.remove();
    } else {
      shimmerText.remove();
    }
  }
  
  // Очищаємо контент
  body.innerHTML='';

  // Повідомлення асистента з SSE-друком
  const assistantMsg = document.createElement('div');
  assistantMsg.className = 'assistant-message typing';
  assistantMsg.textContent = '';
  body.appendChild(assistantMsg);

  // Функція для рендеру решти контенту (категорії/карусель) ПІСЛЯ завершення друку
  const renderRest = () => {
    // Кнопки категорій - показуємо тільки один ряд
    let categoriesToShow = [];
    
    // Пріоритет: спочатку перевіряємо контекст (для фільтрації), потім actions (для першого пошуку)
    if (chatDialogContext && chatDialogContext.available_categories && chatDialogContext.available_categories.length > 0) {
      // Використовуємо категорії з контексту для фільтрації
      categoriesToShow = chatDialogContext.available_categories.map(catCode => ({
        code: catCode,
        label: CATEGORY_SCHEMA[catCode]?.label || catCode,
        isActive: chatDialogContext.current_filter === catCode
      }));
    } else if (Array.isArray(actions) && actions.length > 0) {
      // Використовуємо actions для першого пошуку
      categoriesToShow = actions
        .filter(action => action?.type === 'button' && action?.action === 'select_category')
        .map(action => ({
          code: action.value,
          label: action.label || action.value,
          isActive: false
        }));
    }
    
    // Показуємо кнопки категорій
    if (categoriesToShow.length > 0) {
      const categoriesWrap = document.createElement('div');
      categoriesWrap.className = 'categories-wrap';
      categoriesWrap.style.cssText='display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 6px 0;';
      
      // Завжди показуємо заголовок "Фільтри:"
      categoriesWrap.innerHTML = '<div style="font-size:12px;color:#666;margin-right:8px;align-self:center;">Фільтри:</div>';
      
      categoriesToShow.forEach(cat => {
        const btn = document.createElement('button');
        btn.textContent = cat.label;
        btn.style.cssText = cat.isActive 
          ? 'background:#ffd24d;border:none;border-radius:18px;padding:8px 12px;cursor:pointer;font-size:13px;font-weight:normal;user-select:none;-webkit-user-select:none;'
          : 'background:#fff;border:1px solid #e0e0e0;border-radius:18px;padding:8px 12px;cursor:pointer;font-size:13px;font-weight:normal;user-select:none;-webkit-user-select:none;';
        const parentSection = body.closest('.query-section');
        const stepId = parentSection ? Number(parentSection.dataset.step) : undefined;
        btn.onclick = () => runChatRound({ type: 'category', value: cat.code, valueLabel: cat.label, sectionId: stepId });
        // Додатково вимикаємо виділення при mousedown/drag
        btn.addEventListener('mousedown', (e) => { e.preventDefault(); });
        categoriesWrap.appendChild(btn);
      });
      body.appendChild(categoriesWrap);
    }

    // Якщо нема товарів — не показуємо карусель
    if (!products || products.length === 0) {
      return;
    }

    // Створюємо контейнер для каруселі з кнопками
    const carouselContainer = document.createElement('div');
    carouselContainer.className = 'carousel-container';
    
    const carousel=document.createElement('div');
    carousel.className='products-carousel compact';
    
    // Додаємо drag scroll функціональність
    addDragScrollToCarousel(carousel);
    
    let totalProductsCount = 0; // Визначаємо зовні для доступу пізніше
    
    if(products.length===0){
      carousel.innerHTML=`<div class="result-placeholder"><p>Нічого не знайдено.</p></div>`;
    }else{
      // Показуємо ВСІ товари: спершу рекомендовані
      const recoIds = Array.isArray(recommendations) ? recommendations.map(r => r.product_id) : [];
      const byId = new Map(products.map(p => [p.id, p]));
      const recommended = recoIds.map(id => byId.get(id)).filter(Boolean);
      const remaining = products.filter(p => !recoIds.includes(p.id));
      const sortedProducts = [...recommended, ...remaining];
      totalProductsCount = sortedProducts.length; // Зберігаємо для expandButton
      
      sortedProducts.forEach((p, index)=>{
        const card=document.createElement('div');
        card.className='product-card';
        card.dataset.id=p.id;
        card.dataset.uuid=p.uuid;
        
        // Додаємо клік на всю карточку для додавання в кошик
        card.onclick = async (e) => {
          e.preventDefault();
          e.stopPropagation();
          
          // Перевіряємо, чи товар ще завантажується
          if (card.classList.contains('loading')) {
            return;
          }
          
          await toggleCartItem(p);
        };
        
        // Додаємо індикатор рекомендації для рекомендованих товарів
        const isRecommended = recoIds.includes(p.id);
        const recommendationBadge = isRecommended ? '<div class="recommendation-badge">⭐ Рекомендовано</div>' : '';
        
        card.innerHTML=`
          ${recommendationBadge}
          <div class="product-image-container">
            <div class="image-placeholder">Завантаження...</div>
          </div>
          <div class="product-details">
            <h3>${escapeHTML(p.title_ua||'Без назви')}</h3>
            <p>${escapeHTML((p.description_ua||'').slice(0,100))}...</p>
            <div class="product-pricing-info">
              <div class="rating-placeholder"></div>
              <div class="price-placeholder">Завантаження ціни...</div>
            </div>
          </div>`;
        carousel.appendChild(card);
        
        // Додаємо клас завантаження
        card.classList.add('loading');
        
        // Завантажуємо дані паралельно
        const priceElement = card.querySelector('.price-placeholder');
        const ratingElement = card.querySelector('.rating-placeholder');
        const imageElement = card.querySelector('.product-image-container');
        
        // Додаємо good_code як data-атрибут для lazy loading
        imageElement.dataset.goodCode = p.good_code;
        
        // Ініціалізуємо observer якщо ще не ініційований
        initImageObserver();
        
        // Додаємо контейнер зображення до observer для lazy loading
        imageObserver.observe(imageElement);
        
        // Found elements for chat product
        Promise.all([
          loadProductPrice(priceElement, p.good_code, p),
          loadProductRating(ratingElement, p.good_code, p)
        ]).finally(() => {
          // Прибираємо клас завантаження після завершення всіх запитів
          card.classList.remove('loading');
        });
      });
    }
    
    // Додаємо кнопки навігації
    const prevBtn = document.createElement('button');
    prevBtn.className = 'carousel-nav-btn prev';
    prevBtn.innerHTML = '‹';
    prevBtn.onclick = () => scrollCarousel(carousel, 'prev');
    
    const nextBtn = document.createElement('button');
    nextBtn.className = 'carousel-nav-btn next';
    nextBtn.innerHTML = '›';
    nextBtn.onclick = () => scrollCarousel(carousel, 'next');
    
    // Індикатори видалені
    
    // Складаємо все разом (хінт видалено)
    carouselContainer.appendChild(prevBtn);
    carouselContainer.appendChild(nextBtn);
    carouselContainer.appendChild(carousel);
    
    // Додаємо кнопку розгортання каруселі (якщо є товари)
    if (totalProductsCount > 0) {
      const expandContainer = createExpandToggleButton(carouselContainer, totalProductsCount);
      carouselContainer.appendChild(expandContainer);
    }
    
    // Оновлюємо стан кнопок при прокрутці
    carousel.addEventListener('scroll', () => updateCarouselState(carousel, prevBtn, nextBtn));
    
    body.appendChild(carouselContainer);
    
    // Відновлюємо стан каруселі з sessionStorage
    restoreCarouselState(carouselContainer);

    // Блок рекомендацій AI прибрано за вимогою
  };

  // Показуємо текст асистента одразу без ефекту друку
  const messageText = advice || 'Ось підібрані товари.';
  // Конвертуємо \n в <br>
  assistantMsg.innerHTML = messageText.replace(/\n/g, '<br>');
  assistantMsg.classList.remove('typing');
  
  // Рендеримо категорії та карусель одразу
  renderRest();
}

// Фінальна секція БЕЗ друку тексту (для SSE-режиму, текст вже є)
function finalizeSectionWithoutTextTyping(bodyEl, {products, recommendations = [], actions = null}){
  // Кнопки категорій
  let categoriesToShow = [];
  
  if (chatDialogContext && chatDialogContext.available_categories && chatDialogContext.available_categories.length > 0) {
    categoriesToShow = chatDialogContext.available_categories.map(catCode => ({
      code: catCode,
      label: CATEGORY_SCHEMA[catCode]?.label || catCode,
      isActive: chatDialogContext.current_filter === catCode
    }));
  } else if (Array.isArray(actions) && actions.length > 0) {
    categoriesToShow = actions
      .filter(action => action?.type === 'button' && action?.action === 'select_category')
      .map(action => ({
        code: action.value,
        label: action.label || action.value,
        isActive: false
      }));
  }
  
  // Показуємо кнопки категорій
  if (categoriesToShow.length > 0) {
    const categoriesWrap = document.createElement('div');
    categoriesWrap.className = 'categories-wrap';
    categoriesWrap.style.cssText='display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 6px 0;';
    
    // Завжди показуємо заголовок "Фільтри:"
    categoriesWrap.innerHTML = '<div style="font-size:12px;color:#666;margin-right:8px;align-self:center;">Фільтри:</div>';
    
    categoriesToShow.forEach(cat => {
      const btn = document.createElement('button');
      btn.textContent = cat.label;
        btn.style.cssText = cat.isActive 
          ? 'background:#ffd24d;border:none;border-radius:18px;padding:8px 12px;cursor:pointer;font-size:13px;font-weight:normal;user-select:none;'
          : 'background:#fff;border:1px solid #e0e0e0;border-radius:18px;padding:8px 12px;cursor:pointer;font-size:13px;font-weight:normal;user-select:none;';
      const parentSection = bodyEl.closest('.query-section');
      const stepId = parentSection ? Number(parentSection.dataset.step) : undefined;
      btn.onclick = () => runChatRound({ type: 'category', value: cat.code, valueLabel: cat.label, sectionId: stepId });
      btn.addEventListener('mousedown', (e) => { e.preventDefault(); });
      categoriesWrap.appendChild(btn);
    });
    bodyEl.appendChild(categoriesWrap);
  }

  // Карусель (копіюємо логіку з renderRest)
  if (!products || products.length === 0) return;

  const carouselContainer = document.createElement('div');
  carouselContainer.className = 'carousel-container';
  
  const carousel = document.createElement('div');
  carousel.className = 'products-carousel compact';
  addDragScrollToCarousel(carousel);
  
  const recoIds = Array.isArray(recommendations) ? recommendations.map(r => r.product_id) : [];
  const byId = new Map(products.map(p => [p.id, p]));
  const recommended = recoIds.map(id => byId.get(id)).filter(Boolean);
  const remaining = products.filter(p => !recoIds.includes(p.id));
  const sortedProducts = [...recommended, ...remaining];
  
  sortedProducts.forEach((p)=>{
    const card = document.createElement('div');
    card.className = 'product-card';
    card.dataset.id = p.id;
    card.dataset.uuid = p.uuid;
    
    card.onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (card.classList.contains('loading')) return;
      await toggleCartItem(p);
    };
    
    const isRecommended = recoIds.includes(p.id);
    const recommendationBadge = isRecommended ? '<div class="recommendation-badge">⭐ Рекомендовано</div>' : '';
    
    card.innerHTML=`
      ${recommendationBadge}
      <div class="product-image-container"><div class="image-placeholder">Завантаження...</div></div>
      <div class="product-details">
        <h3>${escapeHTML(p.title_ua||'Без назви')}</h3>
        <p>${escapeHTML((p.description_ua||'').slice(0,100))}...</p>
        <div class="product-pricing-info">
          <div class="rating-placeholder"></div>
          <div class="price-placeholder">Завантаження ціни...</div>
        </div>
      </div>`;
    carousel.appendChild(card);
    card.classList.add('loading');
    
    const priceElement = card.querySelector('.price-placeholder');
    const ratingElement = card.querySelector('.rating-placeholder');
    const imageElement = card.querySelector('.product-image-container');
    
    // Додаємо good_code як data-атрибут для lazy loading
    imageElement.dataset.goodCode = p.good_code;
    
    // Ініціалізуємо observer якщо ще не ініційований
    initImageObserver();
    
    // Додаємо контейнер зображення до observer для lazy loading
    imageObserver.observe(imageElement);
    
    Promise.all([
      loadProductPrice(priceElement, p.good_code, p),
      loadProductRating(ratingElement, p.good_code, p)
    ]).finally(() => {
      card.classList.remove('loading');
    });
  });
  
  const prevBtn = document.createElement('button');
  prevBtn.className = 'carousel-nav-btn prev';
  prevBtn.innerHTML = '‹';
  prevBtn.onclick = () => scrollCarousel(carousel, 'prev');
  
  const nextBtn = document.createElement('button');
  nextBtn.className = 'carousel-nav-btn next';
  nextBtn.innerHTML = '›';
  nextBtn.onclick = () => scrollCarousel(carousel, 'next');
  
  // Індикатори видалені
  
  carouselContainer.appendChild(prevBtn);
  carouselContainer.appendChild(nextBtn);
  carouselContainer.appendChild(carousel);
  
  // Додаємо кнопку розгортання каруселі ПОСЛЯ індикаторів
  const expandContainer = createExpandToggleButton(carouselContainer, sortedProducts.length);
  carouselContainer.appendChild(expandContainer);
  
  carousel.addEventListener('scroll', () => updateCarouselState(carousel, prevBtn, nextBtn));
  bodyEl.appendChild(carouselContainer);
  
  // Відновлюємо стан каруселі з sessionStorage
  restoreCarouselState(carouselContainer);
}

// --- Функції для каруселі ---
function scrollCarousel(carousel, direction) {
  const cards = carousel.querySelectorAll('.product-card');
  if (cards.length === 0) return;
  
  // Вимірюємо реальну відстань між картками
  let cardSpacing = 218; // за замовчуванням: 210 (ширина) + 8 (gap)
  
  if (cards.length >= 2) {
    // Вимірюємо реальну відстань між початками перших двох карток
    const firstCardRect = cards[0].getBoundingClientRect();
    const secondCardRect = cards[1].getBoundingClientRect();
    cardSpacing = secondCardRect.left - firstCardRect.left;
  }
  
  const cardsToScroll = 3;
  
  // Отримуємо поточну позицію
  const currentScroll = carousel.scrollLeft;
  
  // Визначаємо індекс поточної "першої" видимої картки
  const currentCardIndex = Math.round(currentScroll / cardSpacing);
  
  let targetCardIndex;
  
  if (direction === 'prev') {
    // Прокручуємо назад на 3 картки
    targetCardIndex = Math.max(0, currentCardIndex - cardsToScroll);
  } else {
    // Прокручуємо вперед на 3 картки
    targetCardIndex = Math.min(cards.length - 1, currentCardIndex + cardsToScroll);
  }
  
  // Обчислюємо точну позицію цільової картки
  const targetScroll = targetCardIndex * cardSpacing;
  
  // Прокручуємо до точної позиції
  carousel.scrollTo({ left: targetScroll, behavior: 'smooth' });
}

// Функція scrollToPage видалена - індикатори більше не використовуються

function updateCarouselState(carousel, prevBtn, nextBtn) {
  const scrollLeft = carousel.scrollLeft;
  const maxScroll = carousel.scrollWidth - carousel.clientWidth;
  
  // Оновлюємо кнопки
  prevBtn.disabled = scrollLeft <= 0;
  nextBtn.disabled = scrollLeft >= maxScroll - 10; // невеликий допуск
}

// Функція перемикання режиму відображення каруселі з плавною анімацією
function toggleCarouselView(carouselContainer) {
  const carousel = carouselContainer.querySelector('.products-carousel');
  const toggleBtn = carouselContainer.querySelector('.expand-toggle-btn');
  const prevBtn = carouselContainer.querySelector('.carousel-nav-btn.prev');
  const nextBtn = carouselContainer.querySelector('.carousel-nav-btn.next');
  
  if (!carousel || !toggleBtn) return;
  
  const isExpanded = carousel.classList.contains('expanded');
  const cards = Array.from(carousel.querySelectorAll('.product-card'));
  
  // Блокуємо повторне натискання під час анімації
  if (carousel.classList.contains('animating')) return;
  carousel.classList.add('animating');
  
  if (isExpanded) {
    // ========== ЗГОРТАННЯ ==========
    
    // Підготовка карток до анімації
    cards.forEach((card, index) => {
      card.style.opacity = '0';
      card.style.transform = 'scale(0.95)';
    });
    
    // Прибираємо клас expanded
    carousel.classList.remove('expanded');
    toggleBtn.classList.remove('expanded');
    toggleBtn.innerHTML = 'Показати всі товари <span class="expand-icon">↓</span>';
    
    // Показуємо кнопки навігації
    if (prevBtn) prevBtn.style.display = 'flex';
    if (nextBtn) nextBtn.style.display = 'flex';
    
    // Прокручуємо до початку
    carousel.scrollTo({ left: 0, behavior: 'smooth' });
    
    // Анімуємо картки
    requestAnimationFrame(() => {
      cards.forEach((card, index) => {
        card.style.transition = 'opacity 0.8s ease-in-out, transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)';
        card.style.transitionDelay = `${index * 0.015}s`;
        
        requestAnimationFrame(() => {
          card.style.opacity = '1';
          card.style.transform = 'scale(1)';
        });
      });
    });
    
    // Очищаємо стилі після анімації
    setTimeout(() => {
      cards.forEach(card => {
        card.style.opacity = '';
        card.style.transform = '';
        card.style.transition = '';
        card.style.transitionDelay = '';
      });
      carousel.classList.remove('animating');
    }, 800 + cards.length * 15);
    
  } else {
    // ========== РОЗГОРТАННЯ ==========
    
    // Ховаємо кнопки навігації
    if (prevBtn) prevBtn.style.display = 'none';
    if (nextBtn) nextBtn.style.display = 'none';
    
    // Підготовка карток до анімації
    cards.forEach((card, index) => {
      card.style.opacity = '0';
      card.style.transform = 'scale(0.95)';
    });
    
    // Додаємо клас expanded
    carousel.classList.add('expanded');
    toggleBtn.classList.add('expanded');
    toggleBtn.innerHTML = 'Показати менше <span class="expand-icon" style="transform: rotate(180deg);">↓</span>';
    
    // Анімуємо картки (поява)
    requestAnimationFrame(() => {
      cards.forEach((card, index) => {
        card.style.transition = 'opacity 0.8s ease-in-out, transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)';
        card.style.transitionDelay = `${index * 0.015}s`;
        
        requestAnimationFrame(() => {
          card.style.opacity = '1';
          card.style.transform = 'scale(1)';
        });
      });
    });
    
    // Очищаємо стилі після анімації
    setTimeout(() => {
      cards.forEach(card => {
        card.style.opacity = '';
        card.style.transform = '';
        card.style.transition = '';
        card.style.transitionDelay = '';
      });
      carousel.classList.remove('animating');
    }, 800 + cards.length * 15);
  }
}

// Функція створення кнопки розгортання каруселі
function createExpandToggleButton(carouselContainer, productCount) {
  const expandContainer = document.createElement('div');
  expandContainer.className = 'carousel-expand-container';
  
  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'expand-toggle-btn';
  toggleBtn.innerHTML = `Показати всі товари (${productCount}) <span class="expand-icon">↓</span>`;
  toggleBtn.onclick = () => toggleCarouselView(carouselContainer);
  
  expandContainer.appendChild(toggleBtn);
  return expandContainer;
}

// Функція відновлення стану каруселі (завжди компактний режим)
function restoreCarouselState(carouselContainer) {
  // Завжди починаємо з компактного режиму - стан не зберігається
  return;
}

// Функція для швидкого пошуку через кнопки
let isQuickSearchRunning = false;

function performQuickSearch(event, query) {
  // Зупиняємо всплиття події
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  
  // Захист від подвійного виклику
  if (isQuickSearchRunning) {
    return false;
  }
  
  isQuickSearchRunning = true;
  
  // Ховаємо швидкі кнопки
  const quickButtons = document.getElementById('quickSearchButtons');
  if (quickButtons) {
    quickButtons.style.display = 'none';
  }
  
  // Викликаємо performChatSearch напряму з запитом
  performChatSearch(query);
  
  // Скидаємо прапорець через 1 секунду
  setTimeout(() => { 
    isQuickSearchRunning = false;
  }, 1000);
  
  return true;
}

// Функція для активації пошукової строки при кліку
function activateSearchBox() {
  const searchInput = document.getElementById('chatSearchInput');
  if (searchInput) {
    searchInput.focus();
  }
}

// Функція для кнопки пошуку (щоб не активувала input)
function handleSearchButtonClick(event) {
  event.stopPropagation(); // Зупиняємо всплыття події
  
  const btn = document.getElementById('chatSearchButton');
  // Якщо кнопка має клас 'searching', це означає що пошук активний - скасовуємо його
  if (btn && btn.classList.contains('searching')) {
    cancelChatSearch();
  } else {
    // Інакше запускаємо новий пошук
    performChatSearch();
  }
}


function setSectionError(section,msg){
  const body=section.querySelector('.query-body');
  body.innerHTML=`<div class="result-placeholder"><p style="color:red;">Помилка: ${escapeHTML(msg)}</p></div>`;
}

// --- Завантаження фото ---
// Глобальний кеш фоток
const imageCache = new Map();
// Глобальний кеш рейтингів
const ratingsCache = new Map();

// Система черги для завантаження зображень
class ImageLoadQueue {
  constructor(maxConcurrent = 6) {
    this.maxConcurrent = maxConcurrent;
    this.currentLoading = 0;
    this.queue = [];
  }

  async add(fn) {
    // Якщо вже завантажується багато зображень, додаємо в чергу
    if (this.currentLoading >= this.maxConcurrent) {
      return new Promise(resolve => {
        this.queue.push({ fn, resolve });
      });
    }

    // Інакше виконуємо одразу
    this.currentLoading++;
    try {
      await fn();
    } finally {
      this.currentLoading--;
      this.processQueue();
    }
  }

  processQueue() {
    if (this.queue.length > 0 && this.currentLoading < this.maxConcurrent) {
      const { fn, resolve } = this.queue.shift();
      this.currentLoading++;
      fn().finally(() => {
        this.currentLoading--;
        resolve();
        this.processQueue();
      });
    }
  }
}

// Створюємо глобальну чергу з обмеженням 6 паралельних завантажень
const imageLoadQueue = new ImageLoadQueue(6);

// Intersection Observer для lazy loading
let imageObserver = null;

function initImageObserver() {
  if (imageObserver) return;
  
  imageObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const container = entry.target;
        const goodCode = container.dataset.goodCode;
        if (goodCode && !container.dataset.loading) {
          container.dataset.loading = 'true';
          imageObserver.unobserve(container);
          loadProductImageQueued(container, goodCode);
        }
      }
    });
  }, {
    root: null,
    rootMargin: '50px', // Завантажувати трохи заздалегідь
    threshold: 0.01
  });
}

// Обгортка для завантаження з чергою
async function loadProductImageQueued(containerElement, goodCode) {
  await imageLoadQueue.add(() => loadProductImage(containerElement, goodCode));
}

async function loadProductImage(containerElement, goodCode){
  // Перевіряємо чи вже є картинка
  const existingImg = containerElement.querySelector('img');
  if (existingImg) {
    return;
  }
  
  // Перевіряємо кеш
  if (imageCache.has(goodCode)) {
    const img = document.createElement('img');
    img.src = imageCache.get(goodCode);
    img.alt = 'Фото';
    img.className = 'product-image';
    
    // Зберігаємо значок знижки, якщо він є
    const discountBadge = containerElement.querySelector('.cart-discount-badge');
    
    containerElement.innerHTML = '';
    containerElement.appendChild(img);
    
    // Відновлюємо значок знижки, якщо він був
    if (discountBadge) {
      containerElement.appendChild(discountBadge);
    }
    return;
  }
  
  const placeholder = containerElement.querySelector('.image-placeholder') || containerElement;
  if(!goodCode){ if(placeholder) placeholder.textContent='Фото немає'; return; }
  
  try{
    const response = await fetch("https://api.ta-da.net.ua/v1.2/mobile/find.gcode",{
      method:"POST",
      headers:{ "Content-Type":"application/json","Authorization":TA_DA_API_TOKEN,"User-Language":"ua"},
      body:JSON.stringify({shop_id:"8", good_code:goodCode})
    });
    if(!response.ok) {
      // Тихо обробляємо помилки API
      if(placeholder) placeholder.textContent='Фото недоступне';
      return;
    }
    const data = await response.json();
    if(data && data.photo){
      // Зберігаємо в кеш
      imageCache.set(goodCode, data.photo);
      
      const img=document.createElement("img");
      img.src=data.photo; img.alt="Фото"; img.className='product-image';
      
      // Зберігаємо значок знижки, якщо він є
      const discountBadge = containerElement.querySelector('.cart-discount-badge');
      
      containerElement.innerHTML=''; 
      containerElement.appendChild(img);
      
      // Відновлюємо значок знижки, якщо він був
      if (discountBadge) {
        containerElement.appendChild(discountBadge);
      }
    }else{ 
      if(placeholder) placeholder.textContent='Фото немає'; 
    }
  }catch(err){
    // Тихо обробляємо помилки API
    if(placeholder) placeholder.textContent='Фото недоступне';
  }
}



// --- Завантаження рейтингу ---
async function loadProductRating(containerElement, goodCode, product = null){
  // Ховаємо контейнер за замовчуванням, щоб не було "мигання" пустого блоку
  if (containerElement) {
    containerElement.style.visibility = 'hidden';
    containerElement.style.minHeight = '18px';
  }
  if(!goodCode || goodCode === 'undefined' || goodCode === 'null'){ 
    // немає коду — нічого не показуємо
    if (containerElement) containerElement.style.visibility = 'hidden';
    return; 
  }

  // 1) Рендеримо із кешу, якщо доступний — без мережевого запиту
  try {
    if (ratingsCache.has(goodCode)) {
      const rating = ratingsCache.get(goodCode);
      if (!(rating > 0)) { containerElement.style.visibility = 'hidden'; return; }

      if(product) { product.rating = rating; }

      containerElement.style.visibility = 'visible';
      const ratingDiv = document.createElement("div");
      ratingDiv.className = 'product-rating';
      ratingDiv.style.cssText = 'margin: 4px 0; display: flex; align-items: center; gap: 4px;';

      const starsContainer = document.createElement("div");
      starsContainer.style.cssText = 'display: flex; gap: 1px;';
      const fullStars = Math.floor(rating);
      const hasHalfStar = rating % 1 >= 0.5;
      for(let i = 0; i < fullStars; i++) {
        const star = document.createElement("span");
        star.innerHTML = '★';
        star.style.cssText = 'color: #ffc107; font-size: 14px;';
        starsContainer.appendChild(star);
      }
      if(hasHalfStar) {
        const halfStar = document.createElement("span");
        halfStar.innerHTML = '☆';
        halfStar.style.cssText = 'color: #ffc107; font-size: 14px;';
        starsContainer.appendChild(halfStar);
      }
      const emptyStars = 5 - fullStars - (hasHalfStar ? 1 : 0);
      for(let i = 0; i < emptyStars; i++) {
        const emptyStar = document.createElement("span");
        emptyStar.innerHTML = '☆';
        emptyStar.style.cssText = 'color: #ddd; font-size: 14px;';
        starsContainer.appendChild(emptyStar);
      }
      const ratingText = document.createElement("span");
      ratingText.textContent = `(${rating.toFixed(1)})`;
      ratingText.style.cssText = 'color: #666; font-size: 12px; margin-left: 4px;';

      ratingDiv.appendChild(starsContainer);
      ratingDiv.appendChild(ratingText);
      containerElement.innerHTML = '';
      containerElement.appendChild(ratingDiv);
      return;
    }
  } catch(_) { /* ignore cache errors */ }
  
  try{
    const response = await fetch("/api/ta-da/find.gcode",{
      method:"POST",
      headers:{ "Content-Type":"application/json","Authorization":TA_DA_API_TOKEN,"User-Language":"ua"},
      body:JSON.stringify({shop_id:"8", good_code:goodCode})
    });
    if(!response.ok) {
      // Тихо обробляємо помилки API — не показуємо рейтинг
      if (containerElement) containerElement.style.visibility = 'hidden';
      return;
    }
    const data = await response.json();
    
    // Перевіряємо на fallback відповідь
    if (data.error) {
      if (containerElement) containerElement.style.visibility = 'hidden';
      return;
    }
    
    if(data && data.rating !== undefined){
      const rating = parseFloat(data.rating);
      // Показуємо тільки якщо рейтинг позитивний (> 0)
      if (!(rating > 0)) { containerElement.style.visibility = 'hidden'; return; }
      
      // Зберігаємо рейтинг в об'єкт товару, якщо він переданий
      if(product) {
        product.rating = rating;
      }
      // Кладемо в кеш, щоб не перезавантажувати при фільтрах
      try { ratingsCache.set(goodCode, rating); } catch(_) {}
      
      // Показуємо контейнер рейтингу лише коли є значення
      containerElement.style.visibility = 'visible';

      const ratingDiv = document.createElement("div");
      ratingDiv.className = 'product-rating';
      ratingDiv.style.cssText = 'margin: 4px 0; display: flex; align-items: center; gap: 4px;';
      
      // Створюємо зірочки
      const starsContainer = document.createElement("div");
      starsContainer.style.cssText = 'display: flex; gap: 1px;';
      const fullStars = Math.floor(rating);
      const hasHalfStar = rating % 1 >= 0.5;
      
      // Додаємо повні зірочки
      for(let i = 0; i < fullStars; i++) {
        const star = document.createElement("span");
        star.innerHTML = '★';
        star.style.cssText = 'color: #ffc107; font-size: 14px;';
        starsContainer.appendChild(star);
      }
      
      // Додаємо півзірочку якщо потрібно
      if(hasHalfStar) {
        const halfStar = document.createElement("span");
        halfStar.innerHTML = '☆';
        halfStar.style.cssText = 'color: #ffc107; font-size: 14px;';
        starsContainer.appendChild(halfStar);
      }
      
      // Додаємо порожні зірочки
      const emptyStars = 5 - fullStars - (hasHalfStar ? 1 : 0);
      for(let i = 0; i < emptyStars; i++) {
        const emptyStar = document.createElement("span");
        emptyStar.innerHTML = '☆';
        emptyStar.style.cssText = 'color: #ddd; font-size: 14px;';
        starsContainer.appendChild(emptyStar);
      }
      
      // Додаємо числовий рейтинг
      const ratingText = document.createElement("span");
      ratingText.textContent = `(${rating.toFixed(1)})`;
      ratingText.style.cssText = 'color: #666; font-size: 12px; margin-left: 4px;';
      
      ratingDiv.appendChild(starsContainer);
      ratingDiv.appendChild(ratingText);
      
      // Очищаємо контейнер та додаємо рейтинг
      containerElement.innerHTML = '';
      containerElement.appendChild(ratingDiv);
    } else {
      // Немає рейтингу — ховаємо блок повністю
      if (containerElement) containerElement.style.visibility = 'hidden';
    }
  }catch(err){
    // Мовчки ігноруємо помилки рейтингу — ховаємо блок
    if (containerElement) containerElement.style.visibility = 'hidden';
  }
}

// --- Завантаження ціни та наявності ---
async function loadProductPrice(containerElement, goodCode, product = null){
  const placeholder = containerElement; // containerElement вже є .price-placeholder елементом
  
  if(!goodCode || goodCode === 'undefined' || goodCode === 'null'){ 
    if(placeholder) placeholder.textContent='Ціна недоступна'; 
    return; 
  }
  
  // 1) Спроба використати кеш продуктів з цінами (без мережевого запиту)
  try {
    if (productsWithPrices && productsWithPrices.has(goodCode)) {
      const cached = productsWithPrices.get(goodCode);
      const hasDiscount = !!(cached && cached.hasDiscount && cached.originalPrice && cached.price);
      const priceDiv = document.createElement("div");
      priceDiv.className = 'product-price v2';
      priceDiv.style.cssText = 'margin:10px 0 2px 0; display:flex; flex-direction:column; align-items:flex-start; gap:6px;';

      const formatParts = (val) => {
        const n = parseFloat(val);
        const fixed = isFinite(n) ? n.toFixed(2) : '0.00';
        const [m, f] = fixed.split('.');
        return { m, f };
      };

      if (hasDiscount) {
        const old = formatParts(cached.originalPrice);
        const oldLine = document.createElement('div');
        oldLine.className = 'old-price-line';
        oldLine.innerHTML = `<span class="old-price-amount">${old.m}<span class="minor">.${old.f}</span> ₴</span>`;
        priceDiv.appendChild(oldLine);

        const nw = formatParts(cached.price);
        const newLine = document.createElement('div');
        newLine.className = 'new-price-line';
        newLine.innerHTML = `<span class="new-price-amount">${nw.m}<span class="minor">.${nw.f}</span> ₴</span>`;
        priceDiv.appendChild(newLine);
      } else if (cached && cached.price !== undefined) {
        const cur = formatParts(cached.price);
        const only = document.createElement('div');
        only.className = 'new-price-line';
        only.innerHTML = `<span class="new-price-amount">${cur.m}<span class="minor">.${cur.f}</span> ₴</span>`;
        priceDiv.appendChild(only);
      } else {
        // Якщо кеш не містить очікуваних полів — впадемо у мережевий шлях нижче
        throw new Error('no-cached-price-fields');
      }

      containerElement.innerHTML = '';
      containerElement.appendChild(priceDiv);
      // Якщо переданий product — оновимо його значення (уніфікація)
      if (product) {
        product.price = cached.price;
        product.originalPrice = cached.originalPrice;
        product.hasDiscount = cached.hasDiscount;
      }
      return; // успішно відрендерили з кешу
    }
  } catch(_) { /* ignore cache errors */ }
  
  try{
    const response = await fetch("/api/ta-da/find.gcode",{
      method:"POST",
      headers:{ "Content-Type":"application/json","Authorization":TA_DA_API_TOKEN,"User-Language":"ua"},
      body:JSON.stringify({shop_id:"8", good_code:goodCode})
    });
    if(!response.ok) {
      // Тихо обробляємо помилки API
      if(placeholder) placeholder.textContent='Ціна недоступна';
      return;
    }
    const data = await response.json();
    
    // Перевіряємо на fallback відповідь
    if (data.error) {
      if(placeholder) placeholder.textContent='Ціна недоступна';
      return;
    }
    
    if(data && data.price !== undefined){
      // Зберігаємо ціну в об'єкт товару, якщо він переданий
      if(product) {
        product.price = data.discount_price && data.discount_price < data.price ? data.discount_price : data.price;
        product.originalPrice = data.price;
        product.hasDiscount = data.discount_price && data.discount_price < data.price;
        // Кладемо мінімально необхідний снейпшот у кеш для повторних рендерів
        productsWithPrices.set(goodCode, {
          price: product.price,
          originalPrice: product.originalPrice,
          hasDiscount: product.hasDiscount
        });
        
        // Міні-корзина тепер не показує ціни, тільки повідомлення про додавання
      }
      
      const priceDiv = document.createElement("div");
      priceDiv.className = 'product-price v2';
      priceDiv.style.cssText = 'margin:10px 0 2px 0; display:flex; flex-direction:column; align-items:flex-start; gap:6px;';

      const formatParts = (val) => {
        const [m, f] = parseFloat(val).toFixed(2).split('.');
        return { m, f };
      };

      if(data.discount_price && data.discount_price < data.price) {
        const old = formatParts(data.price);
        const oldLine = document.createElement('div');
        oldLine.className = 'old-price-line';
        oldLine.innerHTML = `<span class="old-price-amount">${old.m}<span class="minor">.${old.f}</span> ₴</span>`;
        priceDiv.appendChild(oldLine);

        const nw = formatParts(data.discount_price);
        const newLine = document.createElement('div');
        newLine.className = 'new-price-line';
        newLine.innerHTML = `<span class="new-price-amount">${nw.m}<span class="minor">.${nw.f}</span> ₴</span>`;
        priceDiv.appendChild(newLine);
      } else {
        const cur = formatParts(data.price);
        const only = document.createElement('div');
        only.className = 'new-price-line';
        only.innerHTML = `<span class="new-price-amount">${cur.m}<span class="minor">.${cur.f}</span> ₴</span>`;
        priceDiv.appendChild(only);
      }

      containerElement.innerHTML = '';
      containerElement.appendChild(priceDiv);
    }else{ 
      if(placeholder) placeholder.textContent='Ціна недоступна'; 
    }
  }catch(err){
    // Тихо обробляємо помилки API
    if(placeholder) placeholder.textContent='Ціна недоступна';
  }
}


// --- Рендер простого пошуку ---
function displaySimpleResults(products){
  resultsDivs.simple.innerHTML='';
  if(!products || products.length===0){
    resultsDivs.simple.innerHTML='<div class="result-placeholder"><p>Нічого не знайдено.</p></div>';
    return;
  }
  
  // Показуємо всі релевантні товари (вже відсортовані за score)
  const allProducts = products;
  
  allProducts.forEach((product, index)=>{
    const card=document.createElement('div');
    card.className='product-card';
    card.dataset.id=product.id;
    card.dataset.uuid=product.uuid;
    
    card.innerHTML=`
      <div class="product-image-container">
        <div class="image-placeholder">Завантаження...</div>
      </div>
      <div class="product-details">
        <h3>${escapeHTML(product.title_ua || "Без назви")}</h3>
        <div class="product-pricing-info">
          <div class="rating-placeholder"></div>
          <div class="price-placeholder">Завантаження ціни...</div>
        </div>
        <button class="add-to-cart-btn">
          <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12">
            <path d="M7 18c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12L8.1 13h7.45c.75 0 1.41-.41 1.75-1.03L21.7 4H5.21l-.94-2H1zm16 16c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
          </svg>
          Купити
        </button>
      </div>`;
    resultsDivs.simple.appendChild(card);
    
    // Додаємо клас завантаження
    card.classList.add('loading');
    
    // Завантажуємо дані паралельно
    
    const priceElement = card.querySelector('.price-placeholder');
    const ratingElement = card.querySelector('.rating-placeholder');
    const imageElement = card.querySelector('.product-image-container');
    
    // Додаємо good_code як data-атрибут для lazy loading
    imageElement.dataset.goodCode = product.good_code;
    
    // Ініціалізуємо observer якщо ще не ініційований
    initImageObserver();
    
    // Додаємо контейнер зображення до observer для lazy loading
    imageObserver.observe(imageElement);
    
    // Found elements for product
    
    Promise.all([
      loadProductPrice(priceElement, product.good_code, product),
      loadProductRating(ratingElement, product.good_code, product)
    ]).finally(() => {
      // Прибираємо клас завантаження після завершення всіх запитів
      card.classList.remove('loading');
    });
    
    // Додаємо обробник кліку на кнопку "Купити"
    const addToCartBtn = card.querySelector('.add-to-cart-btn');
    addToCartBtn.onclick = async (e) => {
      e.stopPropagation();
      
      // Перевіряємо, чи товар ще завантажується
      if (card.classList.contains('loading')) {
        return;
      }
      
      
      await toggleCartItem(product);
    };
    
    // Додаємо обробник кліку на фото для локального збільшення
    const imageContainer = card.querySelector('.product-image-container');
    
    if (imageContainer) {
      imageContainer.style.cursor = 'pointer'; // Додаємо курсор pointer
      imageContainer.onclick = (e) => {
        e.stopPropagation();
        
        // Перевіряємо, чи є зображення
        const img = imageContainer.querySelector('img');
        
        if (img && img.src && !img.src.includes('placeholder')) {
          toggleImageZoom(imageContainer);
        } else {
        }
      };
    } else {
    }
    
    // Обробник mouseleave видалено - тепер використовуємо кнопку закриття в overlay
    
    // Видалено клік на всю карточку - тепер товар додається тільки через кнопку "Купити"
  });
}

// --- Функція переміщення привітального повідомлення вгору після пошуку ---
function moveWelcomeMessageUp() {
  if (welcomeMessageMoved) return;
  
  const welcomeMessage = document.querySelector('.assistant-message.welcome-message');
  if (welcomeMessage) {
    welcomeMessage.classList.add('after-search');
    welcomeMessageMoved = true;
  }
}

// --- Привітання асистента ---
function streamWelcomeGreeting() {
  // Перевіряємо, чи вже було показано привітальне повідомлення
  if (welcomeGreetingShown) return;
  
  const thread = document.getElementById('chatThread');
  if (!thread) return;
  
  // Позначаємо, що привітальне повідомлення вже показано
  welcomeGreetingShown = true;
  
  // Спочатку приховуємо приклади
  const aiExamples = document.getElementById('aiExamples');
  if (aiExamples) {
    aiExamples.style.display = 'none';
  }
  
  // Створюємо повідомлення асистента з анімацією друку
  const msgEl = document.createElement('div');
  msgEl.className = 'assistant-message welcome-message';
  msgEl.textContent = '';
  thread.appendChild(msgEl);
  
  // Текст привітання
  const greetingText = '👋 Вітаємо у чат-пошуку! Напишіть що ви шукаєте, або задайте питання.';
  
  // Анімація друку тексту
  let charIndex = 0;
  const typingInterval = setInterval(() => {
    if (charIndex < greetingText.length) {
      msgEl.textContent += greetingText[charIndex];
      charIndex++;
    } else {
      clearInterval(typingInterval);
      
      // Позначаємо що друк завершено
      welcomeTypingComplete = true;
      
      // Після завершення друку показуємо приклади запитів з анімацією кнопок
      // Але тільки якщо не досягнуто ліміт
      const limitCheck = checkChatSearchLimit();
      if (aiExamples && limitCheck.allowed) {
        aiExamples.style.display = 'block';
        
        // Анімуємо появу кнопок по черзі
        const buttons = aiExamples.querySelectorAll('.ai-example-btn');
        buttons.forEach((btn, index) => {
          btn.style.opacity = '0';
          btn.style.transform = 'translateY(20px)';
          
          setTimeout(() => {
            btn.style.transition = 'all 0.4s ease-out';
            btn.style.opacity = '1';
            btn.style.transform = 'translateY(0)';
          }, index * 150); // Затримка між кнопками 150мс
        });
      }
    }
  }, 20);
}

// --- Утиліти ---
function switchPage(pageName){
  for(const key in pages){ pages[key].classList.remove('active'); }
  pages[pageName].classList.add('active');
  
  // Скидаємо стан пошукової строки при переключенні сторінок
  if(pageName === 'simple'){
    const searchBox = document.getElementById('mainChatSearchBox');
    const contentWrapper = document.querySelector('.content-wrapper');
    if (searchBox) {
      searchBox.classList.remove('fixed-bottom');
    }
    if (contentWrapper) {
      contentWrapper.classList.remove('search-fixed');
    }
  }
  
  // Налаштування стану чат-пошуку при переключенні
  if(pageName === 'chat'){
    const chatSearchBox = document.getElementById('chatSearchBox');
    
    if (chatStep === 0) {
      // Початковий стан - пошукова строка по центру
      if (chatSearchBox) {
        chatSearchBox.classList.add('chat-search-box--center');
        chatSearchBox.classList.remove('chat-search-box--footer', 'chat-search-box--footer-static');
      }
      
      // Показуємо привітальне повідомлення від GPT з SSE ефектом
      streamWelcomeGreeting();
    } else {
      // Після пошуку - строка внизу з анімацією
      if (chatSearchBox) {
        chatSearchBox.classList.remove('chat-search-box--center');
        if (!searchBoxAnimationShown) {
          chatSearchBox.classList.add('chat-search-box--footer');
          chatSearchBox.style.animation = 'slideDownToFooter 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards';
          searchBoxAnimationShown = true;
        } else {
          chatSearchBox.classList.add('chat-search-box--footer-static');
          chatSearchBox.style.animation = 'none';
        }
        chatSearchBox.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
        
        // Показуємо білий блок під пошуковою строкою
        const footerMask = document.getElementById('footer-mask');
        if (footerMask) {
          footerMask.style.display = 'block';
        }
      }
    }
  }
  
  // Скидаємо анімації для чат-пошуку при перемиканні
  if(pageName === 'chat'){
    resetChatAnimations();
    // Встановлюємо позицію пошукової строки: по центру тільки якщо ще не було жодного пошуку
    const searchBox = document.getElementById('chatSearchBox');
    const thread = document.getElementById('chatThread');
    // Якщо вже був хоча б один пошук (chatStep > 0), залишаємо строку внизу
    if (searchBox && thread && thread.children.length === 0 && chatStep === 0) {
      searchBox.classList.add('chat-search-box--center');
      searchBox.classList.remove('chat-search-box--footer', 'chat-search-box--footer-static');
      
      // Приховуємо білий блок під пошуковою строкою
      const footerMask = document.getElementById('footer-mask');
      if (footerMask) {
        footerMask.style.display = 'none';
      }
    } else if (searchBox && chatStep > 0) {
      // Якщо вже був пошук, фіксуємо строку внизу (завжди видима на екрані) з анімацією
      searchBox.classList.remove('chat-search-box--center');
      if (!searchBoxAnimationShown) {
        searchBox.classList.add('chat-search-box--footer');
        searchBox.style.animation = 'slideDownToFooter 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards';
        searchBoxAnimationShown = true;
      } else {
        searchBox.classList.add('chat-search-box--footer-static');
        searchBox.style.animation = 'none';
      }
      searchBox.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
      
      // Показуємо білий блок під пошуковою строкою
      const footerMask = document.getElementById('footer-mask');
      if (footerMask) {
        footerMask.style.display = 'block';
      }
    }
    // Запускаємо SSE-привітання ТІЛЬКИ при першому вході (якщо thread порожній)
    if (thread && thread.children.length === 0) {
      streamWelcomeGreeting();
    }
  }

  // Синхронізуємо стан іконок після зміни сторінки
  syncHeaderSearchIcons();
}

function resetChatAnimations(){
  // Функція залишена порожньою - анімації вимкнено
}

// --- Нові функції хедера ---
let currentSearchMode = 'simple'; // 'simple' або 'chat'

// Typewriter анімація для placeholder
const searchPlaceholders = [
  "Футболка",
  "Рукавички",
  "Посуд",
  "Іграшки",
  "Зошити",
  "Свічки",
  "Рушники",
  "Тарілки",
  "М'яч",
  "Пазли"
];

let typewriterIndex = 0;
let charIndex = 0;
let isDeleting = false;
let typewriterTimeout = null;
let isUserTyping = false;

function typewriterEffect() {
  const searchInput = document.getElementById('headerSearchInput');
  
  if (!searchInput || isUserTyping) {
    return;
  }
  
  const currentWord = searchPlaceholders[typewriterIndex];
  
  if (isDeleting) {
    // Стираємо символи
    charIndex--;
    searchInput.placeholder = currentWord.substring(0, charIndex);
    
    if (charIndex === 0) {
      isDeleting = false;
      typewriterIndex = (typewriterIndex + 1) % searchPlaceholders.length;
      typewriterTimeout = setTimeout(typewriterEffect, 500); // Пауза перед наступним словом
    } else {
      typewriterTimeout = setTimeout(typewriterEffect, 50); // Швидкість стирання
    }
  } else {
    // Друкуємо символи
    charIndex++;
    searchInput.placeholder = currentWord.substring(0, charIndex);
    
    if (charIndex === currentWord.length) {
      isDeleting = true;
      typewriterTimeout = setTimeout(typewriterEffect, 2000); // Пауза перед стиранням
    } else {
      typewriterTimeout = setTimeout(typewriterEffect, 100); // Швидкість друку
    }
  }
}

function startTypewriter() {
  const searchInput = document.getElementById('headerSearchInput');
  
  if (searchInput) {
    // Додаємо обробники для відстеження введення користувача
    searchInput.addEventListener('focus', () => {
      isUserTyping = true;
      if (typewriterTimeout) {
        clearTimeout(typewriterTimeout);
      }
      searchInput.placeholder = 'Пошук';
    });
    
    searchInput.addEventListener('blur', () => {
      // Якщо поле порожнє після втрати фокусу, продовжуємо анімацію
      if (!searchInput.value) {
        isUserTyping = false;
        charIndex = 0;
        isDeleting = false;
        typewriterTimeout = setTimeout(typewriterEffect, 1000);
      }
    });
    
    searchInput.addEventListener('input', () => {
      // Якщо користувач почав вводити, зупиняємо анімацію
      if (searchInput.value) {
        isUserTyping = true;
        if (typewriterTimeout) {
          clearTimeout(typewriterTimeout);
        }
      }
    });
    
    // Запускаємо анімацію через 1 секунду після завантаження
    setTimeout(() => {
      if (!searchInput.value) {
        typewriterEffect();
      }
    }, 1000);
  }
}

function switchToSimpleSearch(){
  currentSearchMode = 'simple';
  document.getElementById('simpleSearchIcon').classList.add('active');
  document.getElementById('chatSearchIcon').classList.remove('active');
  switchPage('simple');
  // НЕ очищаємо пошукову строку при перемиканні - залишаємо текст для можливого пошуку
  
  // Очищаємо історію при перемиканні на простий пошук
  clearSearchHistory();
  
  // НЕ скидаємо стан чат-пошуку - залишаємо chatStep як є
  // Тільки приховуємо футер при виході з чат-пошуку
  hideFooter();
  syncHeaderSearchIcons();
}

function switchToChatSearch(){
  currentSearchMode = 'chat';
  document.getElementById('chatSearchIcon').classList.add('active');
  document.getElementById('simpleSearchIcon').classList.remove('active');
  // Додаємо ефект повторного відкриття як у простому пошуку
  const chatPage = document.getElementById('chatSearchPage');
  if (chatPage) {
    chatPage.classList.remove('reopen');
    // перезапуск анімації
    void chatPage.offsetWidth;
    chatPage.classList.add('reopen');
  }
  switchPage('chat');
  
  // Перевіряємо ліміт при перемиканні на чат-пошук
  const limitCheck = checkChatSearchLimit();
  if (!limitCheck.allowed) {
    showChatSearchLimitMessage(limitCheck.minutesLeft);
  } else {
    hideChatSearchLimitMessage();
  }
  
  // НЕ очищаємо пошукову строку при перемиканні - залишаємо текст для можливого пошуку
  
  // Показуємо головну пошукову строку тільки якщо це перший пошук (chatStep === 0) і не заборонено прапорцем
  const mainSearchBox = document.getElementById('mainChatSearchBox');
  if (mainSearchBox) {
    const chatWelcomeSeen = (function(){ try { return sessionStorage.getItem(CHAT_WELCOME_SEEN_KEY) === '1'; } catch(_) { return false; } })();
    if (chatStep === 0 && !chatWelcomeSeen) {
      mainSearchBox.style.display = 'flex';
    } else {
      mainSearchBox.style.display = 'none';
    }
  }
  
  // Показуємо надписи привітання тільки якщо це перший пошук (chatStep === 0) і не заборонено прапорцем
  const chatWelcome = document.querySelector('#chatSearchPage .chat-welcome');
  if (chatWelcome) {
    const chatWelcomeSeen = (function(){ try { return sessionStorage.getItem(CHAT_WELCOME_SEEN_KEY) === '1'; } catch(_) { return false; } })();
    if (chatStep === 0 && !chatWelcomeSeen) {
      chatWelcome.style.display = 'block';
    } else {
      chatWelcome.style.display = 'none';
    }
  }
  
  // Показуємо привітальний блок AI пошуку тільки якщо це перший пошук (chatStep === 0)
  const aiWelcomeContainer = document.getElementById('aiWelcomeContainer');
  if (aiWelcomeContainer) {
    if (chatStep === 0) {
      aiWelcomeContainer.style.display = 'block';
    } else {
      aiWelcomeContainer.style.display = 'none';
    }
  }
  
  // Приклади запитів спочатку приховані, показуються після завершення друку привітання
  const aiExamples = document.getElementById('aiExamples');
  if (aiExamples) {
    const aiLimitCheck = checkChatSearchLimit();
    if (chatStep === 0 && welcomeTypingComplete && aiLimitCheck.allowed) {
      // Якщо друк привітання завершено і ліміт не досягнуто - показуємо приклади
      aiExamples.style.display = 'block';
    } else {
      // В інших випадках - приховуємо приклади
      aiExamples.style.display = 'none';
    }
  }
  
  // Встановлюємо правильну позицію пошукової строки
  const chatSearchBox = document.getElementById('chatSearchBox');
  if (chatSearchBox) {
    if (chatStep === 0) {
      chatSearchBox.classList.add('chat-search-box--center');
      chatSearchBox.classList.remove('chat-search-box--footer', 'chat-search-box--footer-static');
      
      // Приховуємо білий блок під пошуковою строкою
      const footerMask = document.getElementById('footer-mask');
      if (footerMask) {
        footerMask.style.display = 'none';
      }
    } else {
      chatSearchBox.classList.remove('chat-search-box--center');
      if (!searchBoxAnimationShown) {
        chatSearchBox.classList.add('chat-search-box--footer');
        chatSearchBox.style.animation = 'slideDownToFooter 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards';
        searchBoxAnimationShown = true;
      } else {
        chatSearchBox.classList.add('chat-search-box--footer-static');
        chatSearchBox.style.animation = 'none';
      }
      chatSearchBox.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
      
      // Показуємо білий блок під пошуковою строкою
      const footerMask = document.getElementById('footer-mask');
      if (footerMask) {
        footerMask.style.display = 'block';
      }
    }
  }
  
  // Показуємо футер тільки якщо вже був пошук (chatStep > 0)
  if (chatStep > 0) {
    showFooter();
  } else {
    hideFooter();
  }
  syncHeaderSearchIcons();
}

function toggleChatSearch(){
  // Перемикання між звичайним пошуком і чат-пошуком
  if(currentSearchMode === 'chat'){
    // Повертаємося на привітальну сторінку
    currentSearchMode = 'simple'; // Щоб при наступному натисканні знову відкрився чат
    document.getElementById('simpleSearchIcon').classList.remove('active');
    document.getElementById('chatSearchIcon').classList.remove('active');
    switchPage('welcome');
    syncHeaderSearchIcons();
  } else {
    switchToChatSearch();
  }
}

// Функція для активації звичайного пошуку з привітальної сторінки
function activateSimpleSearchFromWelcome() {
  // Прокручуємо сторінку на самий верх плавно
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
  
  // Встановлюємо режим звичайного пошуку (активуємо іконку)
  currentSearchMode = 'simple';
  document.getElementById('simpleSearchIcon').classList.add('active');
  document.getElementById('chatSearchIcon').classList.remove('active');
  syncHeaderSearchIcons();
  
  // Ставимо фокус в пошукову строку хедера з невеликою затримкою
  setTimeout(() => {
    const searchInput = document.getElementById('headerSearchInput');
    if (searchInput) {
      searchInput.focus();
    }
  }, 400); // Затримка щоб анімація прокручування завершилася
}

// Функція для заповнення пошукової строки прикладом запиту (AI пошук)
function fillChatSearchInput(text) {
  const chatInput = document.getElementById('chatSearchInput');
  if (chatInput) {
    chatInput.value = text;
    chatInput.focus();
    
    // Прокручуємо до пошукової строки
    const chatSearchBox = document.getElementById('chatSearchBox');
    if (chatSearchBox) {
      chatSearchBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
}

// Функція для приховування привітального блоку AI пошуку
function hideAIWelcome() {
  const aiWelcomeContainer = document.getElementById('aiWelcomeContainer');
  if (aiWelcomeContainer) {
    aiWelcomeContainer.style.display = 'none';
  }
  
  // Також ховаємо приклади запитів
  const aiExamples = document.getElementById('aiExamples');
  if (aiExamples) {
    aiExamples.style.display = 'none';
  }
}

// Узгодження стану іконок у хедері (колір/фільтр)
function syncHeaderSearchIcons(){
  const simpleIcon = document.getElementById('simpleSearchIcon');
  const chatIcon = document.getElementById('chatSearchIcon');
  const chatImg = chatIcon ? chatIcon.querySelector('img') : null;
  if (!simpleIcon || !chatIcon) return;

  // Визначаємо активну сторінку за DOM, а не за currentSearchMode
  const isChatActive = !!(pages.chat && pages.chat.classList.contains('active'));
  const isSimpleActive = !!(pages.simple && pages.simple.classList.contains('active'));
  const isWelcomeActive = !!(pages.welcome && pages.welcome.classList.contains('active'));

  // Скидаємо активність
  simpleIcon.classList.remove('active');
  chatIcon.classList.remove('active');
  if (chatImg) { chatImg.style.filter = 'grayscale(100%) brightness(60%)'; }

  if (isChatActive) {
    chatIcon.classList.add('active');
    if (chatImg) { chatImg.style.filter = 'none'; }
  } else if (isSimpleActive) {
    simpleIcon.classList.add('active');
    if (chatImg) { chatImg.style.filter = 'grayscale(100%) brightness(60%)'; }
  } else if (isWelcomeActive) {
    // На welcome обидві іконки сірі
    if (chatImg) { chatImg.style.filter = 'grayscale(100%) brightness(60%)'; }
  } else {
    // Фолбек: обидві сірі
    if (chatImg) { chatImg.style.filter = 'grayscale(100%) brightness(60%)'; }
  }
}

function toggleCatalog(){
  // Функція каталогу
}

function toggleDeliveryOptions(){
  // Функція способу отримання
}

function toggleWishlist(){
  // Функція списку бажань
}

function toggleProfile(){
  // Функція профілю
}

function showAuthModal(){
  // Функція авторизації
}

function goToHome(){
  // Повернення на головну сторінку
  switchToSimpleSearch();
  document.getElementById('headerSearchInput').value = '';
  document.getElementById('results-simple').innerHTML = '';
  
  // Скидаємо стан чат-пошуку
  chatStep = 0;
  searchBoxAnimationShown = false; // скидаємо прапор анімації
  const chatThread = document.getElementById('chatThread');
  if (chatThread) {
    chatThread.innerHTML = '';
  }
  
  // Показуємо головну пошукову строку чат-пошуку
  const mainSearchBox = document.getElementById('mainChatSearchBox');
  if (mainSearchBox) {
    mainSearchBox.style.display = 'flex';
    mainSearchBox.classList.remove('fixed-bottom');
  }
  
  // Скидаємо позицію динамічної пошукової строки чату (повертаємо в центр з анімацією)
  const chatSearchBox = document.getElementById('chatSearchBox');
  if (chatSearchBox) {
    chatSearchBox.classList.remove('chat-search-box--footer', 'chat-search-box--footer-static');
    chatSearchBox.classList.add('chat-search-box--center');
    chatSearchBox.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
    chatSearchBox.style.animation = 'none'; // скидаємо анімацію
    
    // Приховуємо білий блок під пошуковою строкою
    const footerMask = document.getElementById('footer-mask');
    if (footerMask) {
      footerMask.style.display = 'none';
    }
  }
  
  // Показуємо надписи привітання при скиданні стану
  const chatWelcome = document.querySelector('.chat-welcome');
  if (chatWelcome) {
    chatWelcome.style.display = 'block';
  }
  
  // Показуємо швидкі кнопки при скиданні стану
  const quickButtons = document.getElementById('quickSearchButtons');
  if (quickButtons) {
    quickButtons.style.display = 'flex';
  }

  // Показуємо вітання для простого пошуку на домашній
  const simpleWelcome = document.getElementById('simpleWelcome');
  if (simpleWelcome) {
    simpleWelcome.style.display = 'block';
  }
  
  // Приховуємо футер при поверненні на головну
  hideFooter();
  
  // Прибираємо класи з content-wrapper
  const contentWrapper = document.querySelector('.content-wrapper');
  if (contentWrapper) {
    contentWrapper.classList.remove('search-fixed');
  }
}

function performSearchFromIcon(){
  // Запуск простого пошуку з іконки лупи
  const query = headerSearchInput.value.trim();
  
  if(query.length === 0 || query.split(/\s+/).length === 0) {
    return;
  }
  
  // Завжди переключаємося на простий пошук при використанні іконки пошуку
  if(currentSearchMode !== 'simple'){
    currentSearchMode = 'simple';
    document.getElementById('simpleSearchIcon').classList.add('active');
    document.getElementById('chatSearchIcon').classList.remove('active');
    syncHeaderSearchIcons();
  }
  
  // Переключаємо сторінку якщо потрібно
  if(!pages.simple.classList.contains('active')){
    switchPage('simple');
    hideFooter();
    clearSearchHistory();
  }
  
  // Виконуємо пошук без затримки
  performSimpleSearch();
}

// Обробники подій
chatSearchInput.addEventListener('keyup', e => { 
  if(e.key === 'Enter') performChatSearch(); 
});

// Показати/сховати кнопку пошуку залежно від наявності тексту
chatSearchInput.addEventListener('input', e => {
  const btn = document.getElementById('chatSearchButton');
  if (e.target.value.trim().length > 0) {
    btn.classList.add('visible');
  } else {
    btn.classList.remove('visible');
  }
});

headerSearchInput.addEventListener('keyup', e => { 
  if(e.key === 'Enter') {
    const query = headerSearchInput.value.trim();
    
    if(query.length === 0 || query.split(/\s+/).length === 0) {
      return;
    }
    
    // Завжди переключаємося на простий пошук при використанні headerSearchInput
    if(currentSearchMode !== 'simple'){
      currentSearchMode = 'simple';
      document.getElementById('simpleSearchIcon').classList.add('active');
      document.getElementById('chatSearchIcon').classList.remove('active');
      syncHeaderSearchIcons();
    }
    
    // Переключаємо сторінку якщо потрібно
    if(!pages.simple.classList.contains('active')){
      switchPage('simple');
      hideFooter();
      clearSearchHistory();
    }
    
    // Виконуємо пошук без затримки
    performSimpleSearch();
  }
});

// Синхронізація пошукових строк відключена - хедер тільки для простого пошуку

// Обробники для кнопок корзини
document.addEventListener('DOMContentLoaded', function() {
  const clearCartBtn = document.getElementById('clear-cart-btn');
  if (clearCartBtn) {
    clearCartBtn.addEventListener('click', clearCart);
  }
  
  const checkoutBtn = document.getElementById('checkout-btn');
  if (checkoutBtn) {
    checkoutBtn.addEventListener('click', function() {
      if (cartItems.length === 0) {
        return;
      }
      alert('Функція оформлення замовлення буде реалізована пізніше.');
    });
  }
});

function escapeHTML(s){
  return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

// Функція для додавання drag scroll до каруселі
function addDragScrollToCarousel(carousel) {
  let isDown = false;
  let startX;
  let scrollLeft;
  let hasDragged = false;
  let dragTimeout = null;

  carousel.addEventListener('mousedown', (e) => {
    // Ігноруємо клік правою кнопкою миші
    if (e.button !== 0) return;
    
    isDown = true;
    hasDragged = false;
    carousel.style.cursor = 'grabbing';
    carousel.style.userSelect = 'none'; // Запобігаємо виділенню тексту
    
    // Використовуємо clientX для точного відстеження
    startX = e.clientX;
    scrollLeft = carousel.scrollLeft;
    
    e.preventDefault();
  });

  carousel.addEventListener('mouseleave', () => {
    if (isDown) {
      isDown = false;
      carousel.style.cursor = 'grab';
      carousel.style.userSelect = '';
      
      // Якщо був drag при виході за межі, блокуємо клік
      if (hasDragged) {
        carousel.classList.add('drag-blocked');
        if (dragTimeout) clearTimeout(dragTimeout);
        dragTimeout = setTimeout(() => {
          carousel.classList.remove('drag-blocked');
        }, 100);
      }
    }
  });

  carousel.addEventListener('mouseup', (e) => {
    if (!isDown) return;
    
    isDown = false;
    carousel.style.cursor = 'grab';
    carousel.style.userSelect = ''; // Відновлюємо можливість виділення
    
    // Якщо був drag, блокуємо клік по товарах
    if (hasDragged) {
      e.preventDefault();
      e.stopPropagation();
      
      // Додаємо клас для блокування кліків
      carousel.classList.add('drag-blocked');
      
      // Через 150мс знімаємо блокування
      if (dragTimeout) clearTimeout(dragTimeout);
      dragTimeout = setTimeout(() => {
        carousel.classList.remove('drag-blocked');
        hasDragged = false;
      }, 150);
    }
  });
  
  // Перехоплюємо click event і блокуємо якщо був drag
  carousel.addEventListener('click', (e) => {
    if (carousel.classList.contains('drag-blocked')) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      return false;
    }
  }, true); // true = capture phase, спрацює раніше за інші обробники

  carousel.addEventListener('mousemove', (e) => {
    if (!isDown) return;
    
    e.preventDefault();
    
    // Використовуємо clientX для точного відстеження
    const x = e.clientX;
    const walk = x - startX;
    const totalWalk = Math.abs(walk);
    
    // Прокручуємо карусель точно відповідно до руху миші
    // Формула: новий scrollLeft = початковий scrollLeft - зсув миші
    carousel.scrollLeft = scrollLeft - walk;
    
    // Позначаємо як drag якщо переміщення більше 3px (для блокування кліку)
    if (totalWalk > 3) {
      hasDragged = true;
    }
  });

  // Запобігаємо drag елементів (зображень тощо)
  carousel.addEventListener('dragstart', (e) => {
    e.preventDefault();
  });

  // Запобігаємо виділенню тексту
  carousel.addEventListener('selectstart', (e) => {
    if (isDown) {
      e.preventDefault();
    }
  });

  // Запобігаємо контекстному меню під час перетягування
  carousel.addEventListener('contextmenu', (e) => {
    if (hasDragged) {
      e.preventDefault();
    }
  });

  // Додаємо курсор grab при наведенні
  carousel.style.cursor = 'grab';
  
  // Додаємо стиль для плавної прокрутки (вимикаємо snap при drag)
  carousel.style.scrollBehavior = 'auto';
}

// Функція показу футера
function showFooter() {
  const footer = document.querySelector('.footer');
  if (footer) {
    footer.classList.add('visible');
    // Додаємо padding-bottom для body коли футер видимий
    document.body.style.paddingBottom = '100px';
  }
}

// Функція приховування футера
function hideFooter() {
  const footer = document.querySelector('.footer');
  if (footer) {
    footer.classList.remove('visible');
    // Прибираємо padding-bottom з body коли футер прихований
    document.body.style.paddingBottom = '0';
  }
}

// Функція пошуку з футера
function performFooterSearch() {
  const searchInput = document.getElementById('footerSearchInput');
  const query = searchInput.value.trim();
  
  if(query.length<2){ 
    return alert("Введіть принаймні 2 символи."); 
  }
  
  if (query) {
    // Переходимо до чат-пошуку
    switchToChatSearch();

    // Очищаємо поле футера перед пошуком
    searchInput.value = '';

    // Скидаємо лише контекст, але НЕ скидаємо історію секцій — новий пошук додається нижче
    chatDialogContext = null;

    // Виконуємо пошук як новий раунд, який додасть нову секцію
    runChatRound({ type: 'text', value: query });
  }
}

// Додаємо обробник Enter для футера
document.addEventListener('DOMContentLoaded', function() {
  const footerSearchInput = document.getElementById('footerSearchInput');
  if (footerSearchInput) {
    footerSearchInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') {
        performFooterSearch();
      }
    });
  }

  // Back-to-top button logic
  const backBtn = document.getElementById('backToTopBtn');
  if (backBtn) {
    backBtn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
  window.addEventListener('scroll', () => { try { updateBackToTopVisibility(); } catch(_){} });
});

function updateBackToTopVisibility() {
  const backBtn = document.getElementById('backToTopBtn');
  if (!backBtn) return;
  const scrolled = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
  // Показуємо кнопку після прокрутки більше половини висоти вікна або > 600px
  const threshold = Math.max(600, Math.floor(window.innerHeight * 0.5));
  backBtn.style.display = scrolled > threshold ? 'flex' : 'none';
}

// --- Міні-корзина ---
let miniCartCounter = 0;
// Таймери автозакриття для кожного елемента міні-корзини
const miniCartTimers = new Map();

function showMiniCart(product) {
  const container = document.getElementById('mini-cart-container');
  
  if (!container) {
    return;
  }
  
  // Встановлюємо інформацію про товар
  const productName = product.title_ua || product.title_ru || 'Товар';
  miniCartCounter++;
  const currentItemId = miniCartCounter; // Зберігаємо ID поточного елемента
  
  // Створюємо новий елемент міні-корзини
  const miniCartItem = document.createElement('div');
  miniCartItem.className = 'mini-cart-item';
  miniCartItem.id = `mini-cart-${currentItemId}`;
  
  miniCartItem.innerHTML = `
    <div class="mini-cart-item-content">
      <div class="mini-cart-item-header">
        <span class="mini-cart-item-title">Товар додано до кошика!</span>
      </div>
      <div class="mini-cart-item-info">
        <div class="mini-cart-item-name">${productName}</div>
        <div class="mini-cart-item-icon" onclick="showFullCart()" style="cursor: pointer;" title="Відкрити повну корзину">
          <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
            <path d="M7 18c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12L8.1 13h7.45c.75 0 1.41-.41 1.75-1.03L21.7 4H5.21l-.94-2H1zm16 16c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
          </svg>
        </div>
      </div>
    </div>
  `;
  
  // Додаємо в контейнер (в кінець, щоб нові з'являлися знизу)
  container.appendChild(miniCartItem);
  
  // Показуємо з невеликою затримкою для анімації
  setTimeout(() => {
    miniCartItem.classList.add('show');
  }, 10);
  
  // Ховаємо через 4 секунди, але з паузою на hover
  const timerId = setTimeout(() => {
    hideMiniCartItem(currentItemId);
  }, 4000);
  miniCartTimers.set(currentItemId, timerId);

  // Зупиняємо таймер при наведенні курсора
  miniCartItem.addEventListener('mouseenter', () => {
    const t = miniCartTimers.get(currentItemId);
    if (t) {
      clearTimeout(t);
      miniCartTimers.delete(currentItemId);
    }
  });

  // Відновлюємо таймер при відведенні курсора
  miniCartItem.addEventListener('mouseleave', () => {
    if (!miniCartTimers.has(currentItemId)) {
      const newTimer = setTimeout(() => {
        hideMiniCartItem(currentItemId);
      }, 1500);
      miniCartTimers.set(currentItemId, newTimer);
    }
  });
}

function hideMiniCartItem(id) {
  const miniCartItem = document.getElementById(`mini-cart-${id}`);
  if (miniCartItem) {
    const t = miniCartTimers.get(id);
    if (t) {
      clearTimeout(t);
      miniCartTimers.delete(id);
    }
    miniCartItem.classList.remove('show');
    // Видаляємо елемент після анімації
    setTimeout(() => {
      if (miniCartItem.parentNode) {
        miniCartItem.parentNode.removeChild(miniCartItem);
      }
    }, 300);
  }
}

function hideMiniCart() {
  // Ховаємо всі міні-корзини
  const container = document.getElementById('mini-cart-container');
  if (container) {
    const items = container.querySelectorAll('.mini-cart-item');
    items.forEach(item => {
      item.classList.remove('show');
      setTimeout(() => {
        if (item.parentNode) {
          item.parentNode.removeChild(item);
        }
      }, 300);
    });
  }
}

// Функція updateMiniCartPrice видалена - тепер не потрібна

function updateCartBadge() {
  const badge = document.getElementById('headerCartBadge');
  if (badge) {
    const totalItems = cartItems.reduce((sum, item) => sum + item.quantity, 0);
    badge.textContent = totalItems;
    if (totalItems > 0) {
      badge.classList.add('visible');
    } else {
      badge.classList.remove('visible');
    }
  } else {
  }
}

// --- Повна корзина ---
function showFullCart() {
  const fullCart = document.getElementById('full-cart');
  if (fullCart) {
    fullCart.classList.add('show');
    renderFullCart();
  }
}

function hideFullCart() {
  const fullCart = document.getElementById('full-cart');
  if (fullCart) {
    fullCart.classList.remove('show');
  }
}


function addItemToFullCart(product) {
  const itemsList = document.getElementById('full-cart-items-list');
  if (!itemsList) return;
  
  // Перевіряємо, чи товар вже є в повній корзині
  const existingItem = itemsList.querySelector(`[data-product-id="${getProductId(product)}"]`);
  if (existingItem) return; // Товар вже є в повній корзині
  
  const item = cartItems.find(i => getProductId(i.product) === getProductId(product));
  if (!item) return;
  
  const quantity = item.quantity;
  const price = parseFloat(product.price) || 0;
  const itemTotal = price * quantity;
  const productName = product.title_ua || product.title_ru || 'Товар';
  
  // Формуємо HTML для ціни з урахуванням знижки
  let priceHtml = '';
  if (product.hasDiscount && product.originalPrice) {
    const originalPrice = parseFloat(product.originalPrice);
    const discountPrice = parseFloat(product.price);
    const discount = Math.round(((originalPrice - discountPrice) / originalPrice) * 100);
    
    priceHtml = `
      <div class="cart-item-price">
        <div class="price-line original-price">${originalPrice.toFixed(2)} ₴</div>
        <div class="price-line discounted-price">${discountPrice.toFixed(2)} ₴</div>
      </div>
    `;
  } else {
    priceHtml = `
      <div class="cart-item-price">
        <div class="price-line total-price">${price.toFixed(2)} ₴</div>
      </div>
    `;
  }
  
  const itemCard = document.createElement('div');
  itemCard.className = 'cart-item-card';
  itemCard.setAttribute('data-product-id', getProductId(product));
  
  // Формуємо HTML для картинки з значком знижки
  let imageHtml = `
    <div class="cart-item-image">
      <div class="image-placeholder">Завантаження...</div>
    </div>
  `;
  
  // Додаємо значок знижки, якщо є знижка
  if (product.hasDiscount && product.originalPrice) {
    const originalPrice = parseFloat(product.originalPrice);
    const discountPrice = parseFloat(product.price);
    const discount = Math.round(((originalPrice - discountPrice) / originalPrice) * 100);
    imageHtml = `
      <div class="cart-item-image">
        <div class="image-placeholder">Завантаження...</div>
        <div class="cart-discount-badge">-${discount}%</div>
      </div>
    `;
  }
  
  itemCard.innerHTML = `
    ${imageHtml}
    <div class="cart-item-details">
      <div class="cart-item-header">
        <div class="cart-item-name">${productName}</div>
        <button class="cart-item-menu" onclick="removeCartItem('${getProductId(product)}')" title="Видалити товар">×</button>
      </div>
      <div class="cart-item-price-info">
        <div class="cart-item-price-label">Ціна за 1 шт.</div>
        <div class="cart-item-price">
          ${priceHtml}
        </div>
      </div>
      <div class="cart-item-quantity-section">
        <div class="cart-item-quantity">
          <button class="quantity-btn" onclick="changeQuantity('${getProductId(product)}', -1)">-</button>
          <span class="quantity-display">${quantity}</span>
          <button class="quantity-btn" onclick="changeQuantity('${getProductId(product)}', 1)">+</button>
        </div>
        <div class="cart-item-total-price">
          <div class="cart-item-total-amount">${itemTotal.toFixed(2)} ₴</div>
        </div>
      </div>
    </div>
  `;
  
  itemsList.appendChild(itemCard);
  
  // Завантажуємо фото для товару в корзині через чергу
  const imageContainer = itemCard.querySelector('.cart-item-image');
  if (imageContainer && product.good_code) {
    loadProductImageQueued(imageContainer, product.good_code);
  }
  
  // Оновлюємо загальний підсумок
  const itemsCount = document.getElementById('full-cart-items-count');
  const totalPrice = document.getElementById('full-cart-total-price');
  
  if (itemsCount && totalPrice) {
    let total = 0;
    const totalItems = cartItems.reduce((sum, item) => sum + item.quantity, 0);
    
    cartItems.forEach((item) => {
      const price = parseFloat(item.product.price) || 0;
      total += price * item.quantity;
    });
    
    itemsCount.textContent = totalItems;
    totalPrice.textContent = `${total.toFixed(2)} ₴`;
  }
}

function updateCartTotals() {
  const itemsCount = document.getElementById('full-cart-items-count');
  const totalPrice = document.getElementById('full-cart-total-price');
  
  if (!itemsCount || !totalPrice) return;
  
  let total = 0;
  const totalItems = cartItems.reduce((sum, item) => sum + item.quantity, 0);
  
  cartItems.forEach((item) => {
    const price = parseFloat(item.product.price) || 0;
    total += price * item.quantity;
  });
  
  itemsCount.textContent = totalItems;
  totalPrice.textContent = `${total.toFixed(2)} ₴`;
}

function renderFullCart() {
  const itemsList = document.getElementById('full-cart-items-list');
  const itemsCount = document.getElementById('full-cart-items-count');
  const totalPrice = document.getElementById('full-cart-total-price');
  const checkoutBtn = document.querySelector('.full-cart-checkout-btn');
  
  if (!itemsList || !itemsCount || !totalPrice) {
    return;
  }
  
  if (cartItems.length === 0) {
    itemsList.innerHTML = '<p class="empty-cart-message">Кошик порожній</p>';
    itemsCount.textContent = '0';
    totalPrice.textContent = '0 ₴';
    
    // Приховуємо кнопку checkout коли корзина пуста
    if (checkoutBtn) {
      checkoutBtn.style.display = 'none';
    }
    return;
  }
  
  // Показуємо кнопку checkout коли є товари
  if (checkoutBtn) {
    checkoutBtn.style.display = 'flex';
  }
  
  // Рендеримо товари
  itemsList.innerHTML = '';
  let total = 0;
  
  cartItems.forEach((item, index) => {
    const product = item.product;
    const quantity = item.quantity;
    const price = parseFloat(product.price) || 0;
    const itemTotal = price * quantity;
    total += itemTotal;
    
    const productName = product.title_ua || product.title_ru || 'Товар';
    const productImage = product.image || '';
    
    // Формуємо HTML для ціни з урахуванням знижки
    let priceHtml = '';
    if (product.hasDiscount && product.originalPrice) {
      const originalPrice = parseFloat(product.originalPrice);
      const discountPrice = parseFloat(product.price);
      const discount = Math.round(((originalPrice - discountPrice) / originalPrice) * 100);
      
      priceHtml = `
        <div class="cart-item-price">
          <div class="price-line original-price">${originalPrice.toFixed(2)} ₴</div>
          <div class="price-line discounted-price">${discountPrice.toFixed(2)} ₴</div>
        </div>
      `;
    } else {
      priceHtml = `
        <div class="cart-item-price">
          <div class="price-line total-price">${price.toFixed(2)} ₴</div>
        </div>
      `;
    }
    
    const itemCard = document.createElement('div');
    itemCard.className = 'cart-item-card';
    itemCard.setAttribute('data-product-id', getProductId(product));
    // Формуємо HTML для картинки з значком знижки
    let imageHtml = `
      <div class="cart-item-image">
        <div class="image-placeholder">Завантаження...</div>
      </div>
    `;
    
    // Додаємо значок знижки, якщо є знижка
    if (product.hasDiscount && product.originalPrice) {
      const originalPrice = parseFloat(product.originalPrice);
      const discountPrice = parseFloat(product.price);
      const discount = Math.round(((originalPrice - discountPrice) / originalPrice) * 100);
      imageHtml = `
        <div class="cart-item-image">
          <div class="image-placeholder">Завантаження...</div>
          <div class="cart-discount-badge">-${discount}%</div>
        </div>
      `;
    }
    
    itemCard.innerHTML = `
      ${imageHtml}
      <div class="cart-item-details">
        <div class="cart-item-header">
          <div class="cart-item-name">${productName}</div>
          <button class="cart-item-menu" onclick="removeCartItem('${getProductId(product)}')" title="Видалити товар">×</button>
        </div>
        <div class="cart-item-price-info">
          <div class="cart-item-price-label">Ціна за 1 шт.</div>
          <div class="cart-item-price">
            ${priceHtml}
          </div>
        </div>
        <div class="cart-item-quantity-section">
          <div class="cart-item-quantity">
            <button class="quantity-btn" onclick="changeQuantity('${getProductId(product)}', -1)">-</button>
            <span class="quantity-display">${quantity}</span>
            <button class="quantity-btn" onclick="changeQuantity('${getProductId(product)}', 1)">+</button>
          </div>
          <div class="cart-item-total-price">
            <div class="cart-item-total-amount">${itemTotal.toFixed(2)} ₴</div>
          </div>
        </div>
      </div>
    `;
    
    itemsList.appendChild(itemCard);
    
    // Завантажуємо фото для товару в корзині через чергу
    const imageContainer = itemCard.querySelector('.cart-item-image');
    if (imageContainer && product.good_code) {
      loadProductImageQueued(imageContainer, product.good_code);
    }
  });
  
  // Оновлюємо підсумок
  updateCartTotals();
}

function removeCartItem(productId) {
  cartItems = cartItems.filter(item => getProductId(item.product) !== productId);
  
  // Видаляємо елемент з DOM
  const itemCard = document.querySelector(`[data-product-id="${productId}"]`);
  if (itemCard) {
    itemCard.remove();
  }
  
  // Оновлюємо підсумок
  if (cartItems.length === 0) {
    const itemsCount = document.getElementById('full-cart-items-count');
    const totalPrice = document.getElementById('full-cart-total-price');
    const checkoutBtn = document.querySelector('.full-cart-checkout-btn');
    
    if (itemsCount) itemsCount.textContent = '0';
    if (totalPrice) totalPrice.textContent = '0 ₴';
    
    // Показуємо повідомлення про порожню корзину
    const itemsList = document.getElementById('full-cart-items-list');
    if (itemsList) {
      itemsList.innerHTML = '<p class="empty-cart-message">Кошик порожній</p>';
    }
    
    // Приховуємо кнопку checkout коли корзина пуста
    if (checkoutBtn) {
      checkoutBtn.style.display = 'none';
    }
  } else {
    updateCartTotals();
    
    // Показуємо кнопку checkout коли є товари
    const checkoutBtn = document.querySelector('.full-cart-checkout-btn');
    if (checkoutBtn) {
      checkoutBtn.style.display = 'flex';
    }
  }
  
  renderCart(); // Оновлюємо старий кошик теж
  renderFullCart(); // Оновлюємо повну корзину
  updateSelectedCards(); // Оновлюємо виділення карток
  updateCartBadge(); // Оновлюємо бейдж в хедері
}

function proceedToCheckout() {
  if (cartItems.length === 0) {
    return;
  }
  // Функція оформлення замовлення буде реалізована пізніше
}

// --- Збільшення фото ---
function showImageZoom(imageSrc) {
  const overlay = document.getElementById('image-zoom-overlay');
  const image = document.getElementById('image-zoom-image');
  
  if (overlay && image) {
    image.src = imageSrc;
    overlay.classList.add('show');
    document.body.style.overflow = 'hidden'; // Блокуємо скрол
  }
}

function closeImageZoom() {
  // Закриваємо всі збільшені картинки
  const overlays = document.querySelectorAll('.image-zoom-overlay.show');
  overlays.forEach(overlay => {
    document.body.removeChild(overlay);
  });
  
  // Скидаємо всі збільшені контейнери
  const zoomedContainers = document.querySelectorAll('.image-container.zoomed');
  zoomedContainers.forEach(container => {
    container.classList.remove('zoomed');
  });
  
  document.body.style.overflow = ''; // Відновлюємо скрол
}

// --- Локальне збільшення фото в простому пошуку ---
function toggleImageZoom(imageContainer) {
  
  // Перевіряємо, чи зображення вже збільшене
  if (imageContainer.classList.contains('zoomed')) {
    resetImageZoom(imageContainer);
  } else {
    zoomImage(imageContainer);
  }
}

function zoomImage(imageContainer) {
  
  // Зберігаємо початкові стилі
  const img = imageContainer.querySelector('img');
  
  if (!img) {
    return;
  }
  
  // Додаємо клас збільшення до оригінального контейнера
  imageContainer.classList.add('zoomed');
  // Піднімаємо картку над сусідніми, щоб не перекривалось
  const parentCard = imageContainer.closest('.product-card');
  if (parentCard) {
    parentCard.style.zIndex = '1000';
    parentCard.style.position = parentCard.style.position || 'relative';
  }
  
  // Додаємо стилі для збільшення в 2 рази на тому ж місці
  imageContainer.style.cssText += `
    transform: scale(2);
    z-index: 9999;
    position: relative;
    transition: transform 0.3s ease;
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
    border-radius: 8px;
    overflow: visible;
    transform-origin: center;
  `;
  
  // Створюємо функції обробників
  const closeZoom = (e) => {
    if (!imageContainer.contains(e.target)) {
      resetImageZoom(imageContainer);
    }
  };
  
  const handleEscape = (e) => {
    if (e.key === 'Escape') {
      resetImageZoom(imageContainer);
    }
  };
  
  const handleMouseLeave = () => {
    resetImageZoom(imageContainer);
  };
  
  // Зберігаємо посилання на функції в контейнері для подальшого видалення
  imageContainer._zoomHandlers = {
    closeZoom,
    handleEscape,
    handleMouseLeave
  };
  
  // Додаємо обробники подій з невеликою затримкою
  setTimeout(() => {
    document.addEventListener('click', closeZoom);
    document.addEventListener('keydown', handleEscape);
    imageContainer.addEventListener('mouseleave', handleMouseLeave);
  }, 100);
}

function resetImageZoom(imageContainer) {
  // Прибираємо клас збільшення
  imageContainer.classList.remove('zoomed');
  
  // Відновлюємо початкові стилі
  imageContainer.style.transform = '';
  imageContainer.style.zIndex = '';
  imageContainer.style.position = '';
  imageContainer.style.transition = '';
  imageContainer.style.boxShadow = '';
  imageContainer.style.borderRadius = '';
  imageContainer.style.overflow = '';
  imageContainer.style.transformOrigin = '';
  // Відновлюємо z-index батьківської картки
  const parentCard = imageContainer.closest('.product-card');
  if (parentCard) {
    parentCard.style.zIndex = '';
    // position не чіпаємо, щоб не ламати layout
  }
  
  // Очищаємо обробники подій, якщо вони існують
  if (imageContainer._zoomHandlers) {
    document.removeEventListener('click', imageContainer._zoomHandlers.closeZoom);
    document.removeEventListener('keydown', imageContainer._zoomHandlers.handleEscape);
    imageContainer.removeEventListener('mouseleave', imageContainer._zoomHandlers.handleMouseLeave);
    delete imageContainer._zoomHandlers;
  }
}

// Закриваємо збільшене фото при натисканні Escape
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closeImageZoom();
  }
});

