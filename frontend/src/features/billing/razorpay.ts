/** Razorpay Checkout: load the script once, open the payment window, resolve with the signed result. */
declare global { interface Window { Razorpay?: any } }

let loading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://checkout.razorpay.com/v1/checkout.js';
    s.onload = () => resolve();
    s.onerror = () => { loading = null; reject(new Error('Could not load Razorpay. Check your internet connection.')); };
    document.body.appendChild(s);
  });
  return loading;
}

export interface RazorpayResult { order_id: string; payment_id: string; signature: string }

export async function payWithRazorpay(order: {
  key_id: string; order_id: string; amount: number; currency: string; name: string; description: string;
  prefill: { name: string; email: string; contact: string };
}): Promise<RazorpayResult | null> {
  await loadScript();
  return new Promise((resolve, reject) => {
    const rz = new window.Razorpay({
      key: order.key_id, order_id: order.order_id, amount: order.amount, currency: order.currency,
      name: order.name, description: order.description, prefill: order.prefill,
      theme: { color: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#9E2B25' },
      handler: (r: any) => resolve({ order_id: r.razorpay_order_id, payment_id: r.razorpay_payment_id, signature: r.razorpay_signature }),
      modal: { ondismiss: () => resolve(null) },
    });
    rz.on('payment.failed', (r: any) => reject(new Error(r?.error?.description || 'The payment failed.')));
    rz.open();
  });
}
