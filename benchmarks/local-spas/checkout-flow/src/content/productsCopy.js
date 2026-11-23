export const DEFAULT_PRODUCTS_LANGUAGE = "en";
export const PRODUCTS_LANGUAGE_OPTIONS = Object.freeze([
  Object.freeze({ code: "en", rootLang: "en" }),
  Object.freeze({ code: "es", rootLang: "es" }),
]);

export const PRODUCTS_COPY_BY_LANGUAGE = deepFreeze({
  en: {
    shell: {
      eyebrow: "Brightlane Shop",
      appName: "Checkout Flow",
    },
    nav: {
      ariaLabel: "Checkout routes",
      products: "Products",
      cart: "Cart",
    },
    footer: {
      brand: "AccessGraph Shop",
      description: "Demo checkout experience",
      copyright: "© 2026 AccessGraph Shop",
    },
    languageSwitcher: {
      ariaLabel: "Products language",
      label: "Language",
      options: {
        en: "English",
        es: "Spanish",
      },
    },
    pageTitles: {
      products: "Products",
      cart: "Cart",
    },
    route: {
      heading: "Products",
      summary: "Browse featured products and update the cart summary.",
    },
    list: {
      heading: "Featured products",
      description: "Browse featured products for your workspace.",
      categoryBrowserHeading: "Browse by category",
      categoryTablistLabel: "Product categories",
    },
    categories: {
      "desk-accessories": {
        label: "Desk accessories",
        description: "Lighting and cable tools for a tidy workspace.",
      },
      "office-supplies": {
        label: "Office supplies",
        description: "Everyday supplies for notes and planning.",
      },
    },
    products: {
      "prod-desk-lamp": {
        category: "Home office",
        name: "Desk lamp",
        imageAlt: "Desk lamp with adjustable brass shade",
      },
      "prod-notebook-set": {
        category: "Stationery",
        name: "Notebook set",
        imageAlt: "Three notebooks with blue, teal, and coral covers",
      },
      "prod-cable-organizer": {
        category: "Accessories",
        name: "Cable organizer",
      },
    },
    productCard: {
      addButtonLabel: "Add {productName}",
      maxButtonLabel: "{productName} at maximum",
      notInCart: "Not in cart",
      inCartPrefix: "In cart",
      itemSingular: "item",
      itemPlural: "items",
    },
    cartSummary: {
      ariaLabel: "Current cart",
      heading: "Cart summary",
      items: "Items",
      subtotal: "Subtotal",
      shipping: "Shipping",
      orderTotal: "Order total",
      itemSingular: "item",
      itemPlural: "items",
    },
    statusMessages: {
      addedToCart: "{productName} added to cart.",
      quantityUpdated: "{productName} quantity updated to {quantity}.",
      maxQuantity: "{productName} is already at maximum quantity {maxQuantity}.",
    },
    support: {
      heading: "Support",
      prompt: "Need help after checkout?",
      shippingHeading: "Shipping help",
      shippingDescription:
        "Learn about delivery times and available shipping options.",
      shippingLabel: "Shipping information",
      returnsLabel: "Returns and refunds",
    },
    cart: {
      route: {
        heading: "Cart",
        summary: "Review cart items and quantity controls.",
      },
      progress: {
        heading: "Checkout progress",
        steps: {
          cart: "Cart",
          address: "Shipping address",
          payment: "Payment",
          review: "Review",
        },
        stateLabels: {
          current: "Current step",
          previous: "Previous step",
          notStarted: "Not started",
        },
      },
      cartSection: {
        heading: "Cart items",
        description:
          "Review selected products before entering checkout details.",
      },
      cartItem: {
        products: {
          "prod-desk-lamp": {
            category: "Home office",
            name: "Desk lamp",
          },
          "prod-notebook-set": {
            category: "Stationery",
            name: "Notebook set",
          },
          "prod-cable-organizer": {
            category: "Accessories",
            name: "Cable organizer",
          },
        },
        unitPrice: "Unit price",
        maxQuantity: "Maximum {maxQuantity} per item.",
        quantityGroupLabel: "{itemName} quantity controls",
        decreaseLabel: "Decrease {itemName} quantity",
        quantityLabel: "{itemName} quantity",
        increaseLabel: "Increase {itemName} quantity",
        lineTotal: "Line total",
      },
      cartSummary: {
        ariaLabel: "Order totals",
        heading: "Cart summary",
        items: "Items",
        subtotal: "Subtotal",
        shipping: "Shipping",
        orderTotal: "Order total",
        itemSingular: "item",
        itemPlural: "items",
      },
      preferences: {
        giftReceipt: "Gift receipt",
        giftReceiptNote: "A gift receipt will be included.",
        saveCart: "Save cart",
        saveCartNote: "Cart saved for later.",
      },
      deliveryEstimate: {
        trigger: "Delivery estimate",
        panel:
          "Standard delivery usually arrives in 3-5 business days after dispatch.",
      },
      shippingInformation: {
        trigger: "Shipping information",
        heading: "Shipping information",
        body:
          "Standard shipping is calculated during checkout. Delivery details are confirmed after you enter the shipping address.",
        close: "Close",
      },
      actions: {
        continueToAddress: "Continue to address",
      },
      emptyCart: {
        heading: "Your cart is empty",
        description: "Add a product before continuing checkout.",
        continue: "Browse products",
      },
      statusMessages: {
        maxQuantity: "{productName} is already at maximum quantity {maxQuantity}.",
        quantityUpdated: "{productName} quantity updated to {quantity}.",
        removed: "{productName} removed from cart.",
      },
    },
  },
  es: {
    shell: {
      eyebrow: "Brightlane Shop",
      appName: "Flujo de compra",
    },
    nav: {
      ariaLabel: "Rutas de compra",
      products: "Productos",
      cart: "Carrito",
    },
    footer: {
      brand: "AccessGraph Shop",
      description: "Experiencia de compra de demostración",
      copyright: "© 2026 AccessGraph Shop",
    },
    languageSwitcher: {
      ariaLabel: "Idioma de productos",
      label: "Idioma",
      options: {
        en: "Inglés",
        es: "Español",
      },
    },
    pageTitles: {
      products: "Productos",
      cart: "Carrito",
    },
    route: {
      heading: "Productos",
      summary: "Explora productos destacados y actualiza el resumen del carrito.",
    },
    list: {
      heading: "Productos destacados",
      description: "Explora productos destacados para tu espacio de trabajo.",
      categoryBrowserHeading: "Explora por categoría",
      categoryTablistLabel: "Categorías de productos",
    },
    categories: {
      "desk-accessories": {
        label: "Accesorios de escritorio",
        description:
          "Iluminación y herramientas para cables para un espacio de trabajo ordenado.",
      },
      "office-supplies": {
        label: "Material de oficina",
        description: "Suministros diarios para notas y planificación.",
      },
    },
    products: {
      "prod-desk-lamp": {
        category: "Oficina en casa",
        name: "Lámpara de escritorio",
        imageAlt:
          "Lámpara de escritorio con pantalla de latón ajustable",
      },
      "prod-notebook-set": {
        category: "Papelería",
        name: "Juego de cuadernos",
        imageAlt:
          "Tres cuadernos con cubiertas de color azul, verde azulado y coral",
      },
      "prod-cable-organizer": {
        category: "Accesorios",
        name: "Organizador de cables",
      },
    },
    productCard: {
      addButtonLabel: "Agregar {productName}",
      maxButtonLabel: "{productName} en cantidad máxima",
      notInCart: "No está en el carrito",
      inCartPrefix: "En el carrito",
      itemSingular: "artículo",
      itemPlural: "artículos",
    },
    cartSummary: {
      ariaLabel: "Carrito actual",
      heading: "Resumen del carrito",
      items: "Artículos",
      subtotal: "Subtotal",
      shipping: "Envío",
      orderTotal: "Total del pedido",
      itemSingular: "artículo",
      itemPlural: "artículos",
    },
    statusMessages: {
      addedToCart: "{productName} agregado al carrito.",
      quantityUpdated: "Cantidad de {productName} actualizada a {quantity}.",
      maxQuantity: "{productName} ya está en la cantidad máxima {maxQuantity}.",
    },
    support: {
      heading: "Ayuda",
      prompt: "¿Necesitas ayuda después de la compra?",
      shippingHeading: "Ayuda con el envío",
      shippingDescription:
        "Consulta los plazos de entrega y las opciones de envío disponibles.",
      shippingLabel: "Información de envío",
      returnsLabel: "Devoluciones y reembolsos",
    },
    cart: {
      route: {
        heading: "Carrito",
        summary: "Revisa los artículos del carrito y los controles de cantidad.",
      },
      progress: {
        heading: "Progreso de compra",
        steps: {
          cart: "Carrito",
          address: "Dirección de envío",
          payment: "Pago",
          review: "Revisión",
        },
        stateLabels: {
          current: "Paso actual",
          previous: "Paso anterior",
          notStarted: "No iniciado",
        },
      },
      cartSection: {
        heading: "Artículos del carrito",
        description:
          "Revisa los productos seleccionados antes de ingresar los detalles de compra.",
      },
      cartItem: {
        products: {
          "prod-desk-lamp": {
            category: "Oficina en casa",
            name: "Lámpara de escritorio",
          },
          "prod-notebook-set": {
            category: "Papelería",
            name: "Juego de cuadernos",
          },
          "prod-cable-organizer": {
            category: "Accesorios",
            name: "Organizador de cables",
          },
        },
        unitPrice: "Precio unitario",
        maxQuantity: "Máximo {maxQuantity} por artículo.",
        quantityGroupLabel: "Controles de cantidad de {itemName}",
        decreaseLabel: "Disminuir cantidad de {itemName}",
        quantityLabel: "Cantidad de {itemName}",
        increaseLabel: "Aumentar cantidad de {itemName}",
        lineTotal: "Total de línea",
      },
      cartSummary: {
        ariaLabel: "Totales del pedido",
        heading: "Resumen del carrito",
        items: "Artículos",
        subtotal: "Subtotal",
        shipping: "Envío",
        orderTotal: "Total del pedido",
        itemSingular: "artículo",
        itemPlural: "artículos",
      },
      preferences: {
        giftReceipt: "Recibo de regalo",
        giftReceiptNote: "Se incluirá un recibo de regalo.",
        saveCart: "Guardar carrito",
        saveCartNote: "Carrito guardado para después.",
      },
      deliveryEstimate: {
        trigger: "Estimación de entrega",
        panel:
          "La entrega estándar suele llegar en 3-5 días hábiles después del envío.",
      },
      shippingInformation: {
        trigger: "Información de envío",
        heading: "Información de envío",
        body:
          "El envío estándar se calcula durante la compra. Los detalles de entrega se confirman después de ingresar la dirección de envío.",
        close: "Cerrar",
      },
      actions: {
        continueToAddress: "Continuar a dirección",
      },
      emptyCart: {
        heading: "Tu carrito está vacío",
        description: "Agrega un producto antes de continuar con la compra.",
        continue: "Explorar productos",
      },
      statusMessages: {
        maxQuantity: "{productName} ya está en cantidad máxima {maxQuantity}.",
        quantityUpdated: "Cantidad de {productName} actualizada a {quantity}.",
        removed: "{productName} eliminado del carrito.",
      },
    },
  },
});

export function getProductsCopyForLanguage(language) {
  return (
    PRODUCTS_COPY_BY_LANGUAGE[language] ??
    PRODUCTS_COPY_BY_LANGUAGE[DEFAULT_PRODUCTS_LANGUAGE]
  );
}

export function getProductsRootLang(language) {
  return (
    PRODUCTS_LANGUAGE_OPTIONS.find((option) => option.code === language)
      ?.rootLang ?? "en"
  );
}

function deepFreeze(value) {
  if (!value || typeof value !== "object") {
    return value;
  }

  for (const child of Object.values(value)) {
    deepFreeze(child);
  }

  return Object.freeze(value);
}
