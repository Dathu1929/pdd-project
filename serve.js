const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 5000;
const BASE_DIR = path.join(__dirname, 'app-new');
const ENV_FILE = path.join(__dirname, 'backend', '.env');

// Helper to load backend/.env if it exists
function loadEnv() {
  const env = {};
  if (fs.existsSync(ENV_FILE)) {
    const lines = fs.readFileSync(ENV_FILE, 'utf8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const idx = trimmed.indexOf('=');
      if (idx !== -1) {
        const key = trimmed.slice(0, idx).trim();
        const val = trimmed.slice(idx + 1).trim();
        env[key] = val;
      }
    }
  }
  return env;
}

let envConfig = loadEnv();

const MIME_TYPES = {
  '.html': 'text/html; charset=UTF-8',
  '.css': 'text/css; charset=UTF-8',
  '.js': 'application/javascript; charset=UTF-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

function parseBody(req) {
  return new Promise((resolve) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        resolve(JSON.parse(body || '{}'));
      } catch (e) {
        resolve({});
      }
    });
  });
}

function sendJson(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
  });
  res.end(JSON.stringify(data));
}

const server = http.createServer(async (req, res) => {
  // Handle CORS Preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    });
    res.end();
    return;
  }

  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = parsedUrl.pathname;

  // ==========================================
  // API: GATEWAY STATUS
  // ==========================================
  if (pathname === '/api/gateway-status' && req.method === 'GET') {
    envConfig = loadEnv();
    return sendJson(res, 200, {
      email: {
        provider: 'resend',
        active: Boolean(envConfig.RESEND_API_KEY && !envConfig.RESEND_API_KEY.includes('your_')),
        fromEmail: envConfig.RESEND_FROM_EMAIL || 'Smart Electricity <onboarding@resend.dev>',
        verifiedOwnerEmail: 'mangapatidattu@gmail.com'
      },
      sms: {
        fast2smsConfigured: Boolean(envConfig.FAST2SMS_API_KEY && envConfig.FAST2SMS_API_KEY.length > 5),
        twilioConfigured: Boolean(envConfig.TWILIO_ACCOUNT_SID && envConfig.TWILIO_AUTH_TOKEN && envConfig.TWILIO_PHONE_NUMBER)
      }
    });
  }

  // ==========================================
  // API: SEND LIVE REAL EMAIL (RESEND API)
  // ==========================================
  if (pathname === '/api/send-email' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      envConfig = loadEnv();

      const apiKey = body.apiKey || envConfig.RESEND_API_KEY;
      if (!apiKey || apiKey.includes('your_')) {
        return sendJson(res, 400, {
          success: false,
          error: 'Resend API key is not configured. Please add RESEND_API_KEY in settings.'
        });
      }

      let toEmail = (body.to || 'mangapatidattu@gmail.com').trim();
      const subject = body.subject || `⚡ Electricity Bill Alert: Bill #${body.bill_no || 'EB95027'}`;
      const consumerName = body.consumer_name || 'Customer';
      const billNo = body.bill_no || 'EB95027';
      const amount = body.amount || '1,450';
      const dueDate = body.due_date || '25 Oct 2026';

      const emailHtml = body.html || `
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width:600px; margin:0 auto; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden;">
          <div style="background:#1877F2; padding:24px 30px; color:#FFFFFF;">
            <h2 style="margin:0; font-size:20px; font-weight:800;">⚡ Smart Electricity Monitoring</h2>
            <p style="margin:6px 0 0 0; opacity:0.9; font-size:13px;">Official Bill Due Reminder</p>
          </div>
          <div style="padding:30px;">
            <p style="font-size:15px; color:#1E293B; margin-top:0;">Hello <strong>${consumerName}</strong>,</p>
            <p style="font-size:14px; color:#475569; line-height:1.6;">This is an automated notification regarding your pending electricity bill payment.</p>
            
            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:18px; margin:20px 0;">
              <table style="width:100%; border-collapse:collapse; font-size:13.5px;">
                <tr>
                  <td style="padding:6px 0; color:#64748B;">Bill Number:</td>
                  <td style="padding:6px 0; font-weight:700; color:#0F172A; text-align:right;">${billNo}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0; color:#64748B;">Total Amount:</td>
                  <td style="padding:6px 0; font-weight:800; color:#1877F2; font-size:16px; text-align:right;">₹${amount}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0; color:#64748B;">Due Date:</td>
                  <td style="padding:6px 0; font-weight:700; color:#DC2626; text-align:right;">${dueDate}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0; color:#64748B;">Status:</td>
                  <td style="padding:6px 0; font-weight:700; color:#F59E0B; text-align:right;">Pending</td>
                </tr>
              </table>
            </div>

            <p style="font-size:13px; color:#64748B; line-height:1.5;">Please pay your bill before <strong>${dueDate}</strong> to avoid disconnection or late payment charges.</p>
            
            <div style="margin-top:25px; text-align:center;">
              <a href="http://localhost:5000/" style="display:inline-block; background:#1877F2; color:#FFFFFF; text-decoration:none; padding:12px 28px; border-radius:30px; font-weight:700; font-size:14px;">Pay Bill in Portal</a>
            </div>
          </div>
          <div style="background:#F1F5F9; padding:16px; text-align:center; font-size:12px; color:#64748B;">
            Sent by Smart Electricity Bill Monitoring System • Real-Time Live Dispatch
          </div>
        </div>
      `;

      // Try sending to requested email
      let resendResp = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          from: envConfig.RESEND_FROM_EMAIL || 'Smart Electricity <onboarding@resend.dev>',
          to: [toEmail],
          subject: subject,
          html: emailHtml
        })
      });

      let resendData = await resendResp.json();

      // If Resend test account restricts sending to unverified domain, fallback to verified owner email
      if (!resendResp.ok && resendData && resendData.message && resendData.message.includes('mangapatidattu@gmail.com')) {
        const ownerEmail = 'mangapatidattu@gmail.com';
        const fallbackResp = await fetch('https://api.resend.com/emails', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${apiKey}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            from: envConfig.RESEND_FROM_EMAIL || 'Smart Electricity <onboarding@resend.dev>',
            to: [ownerEmail],
            subject: `[For: ${toEmail}] ${subject}`,
            html: emailHtml
          })
        });
        const fallbackData = await fallbackResp.json();
        if (fallbackResp.ok) {
          return sendJson(res, 200, {
            success: true,
            message: `Live email delivered to verified inbox (${ownerEmail})!`,
            id: fallbackData.id,
            recipient: ownerEmail,
            originalTarget: toEmail,
            note: 'Delivered to your Resend account email (mangapatidattu@gmail.com).'
          });
        }
      }

      if (!resendResp.ok) {
        return sendJson(res, 400, {
          success: false,
          error: resendData.message || 'Resend API returned an error.'
        });
      }

      return sendJson(res, 200, {
        success: true,
        message: `Live email successfully delivered to ${toEmail}!`,
        id: resendData.id,
        recipient: toEmail
      });
    } catch (err) {
      console.error('Email send error:', err);
      return sendJson(res, 500, { success: false, error: err.message });
    }
  }

  // ==========================================
  // API: SEND LIVE REAL SMS (FAST2SMS OR TWILIO)
  // ==========================================
  if (pathname === '/api/send-sms' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      envConfig = loadEnv();

      const number = (body.number || body.phone || '9876543210').toString().replace(/\D/g, '');
      const message = body.message || `Electricity Bill Alert: Bill #${body.bill_no || 'EB95027'} for Rs.${body.amount || '1450'} is due on ${body.due_date || '25 Oct 2026'}. Pay in portal to avoid late fee.`;
      const provider = body.provider || envConfig.SMS_PROVIDER || 'fast2sms';

      // 1. FAST2SMS PROVIDER
      if (provider === 'fast2sms') {
        const apiKey = body.apiKey || envConfig.FAST2SMS_API_KEY;
        if (!apiKey || apiKey.length < 5) {
          return sendJson(res, 400, {
            success: false,
            error: 'Fast2SMS API Key is missing. Please enter your free Fast2SMS API key in settings or backend/.env.',
            needKey: true,
            provider: 'fast2sms'
          });
        }

        const cleanMobile = number.length > 10 ? number.slice(-10) : number;
        const f2sResp = await fetch('https://www.fast2sms.com/dev/bulkV2', {
          method: 'POST',
          headers: {
            'authorization': apiKey,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            route: 'q',
            message: message,
            language: 'english',
            flash: 0,
            numbers: cleanMobile
          })
        });
        const f2sData = await f2sResp.json();
        if (f2sData.return) {
          return sendJson(res, 200, {
            success: true,
            message: `Real SMS successfully sent to +91 ${cleanMobile} via Fast2SMS!`,
            provider: 'fast2sms',
            recipient: `+91 ${cleanMobile}`,
            data: f2sData
          });
        } else {
          return sendJson(res, 400, {
            success: false,
            error: f2sData.message ? f2sData.message.join(', ') : 'Fast2SMS delivery failed.',
            data: f2sData
          });
        }
      }

      // 2. TWILIO PROVIDER
      if (provider === 'twilio') {
        const accountSid = body.accountSid || envConfig.TWILIO_ACCOUNT_SID;
        const authToken = body.authToken || envConfig.TWILIO_AUTH_TOKEN;
        const fromNumber = body.fromNumber || envConfig.TWILIO_PHONE_NUMBER;

        if (!accountSid || !authToken || !fromNumber) {
          return sendJson(res, 400, {
            success: false,
            error: 'Twilio credentials incomplete. Please configure Account SID, Auth Token & From Number in settings.',
            needKey: true,
            provider: 'twilio'
          });
        }

        const formattedTo = number.startsWith('+') ? number : `+91${number.slice(-10)}`;
        const basicAuth = Buffer.from(`${accountSid}:${authToken}`).toString('base64');
        const formParams = new URLSearchParams();
        formParams.append('To', formattedTo);
        formParams.append('From', fromNumber);
        formParams.append('Body', message);

        const twilioResp = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${accountSid}/Messages.json`, {
          method: 'POST',
          headers: {
            'Authorization': `Basic ${basicAuth}`,
            'Content-Type': 'application/x-www-form-urlencoded'
          },
          body: formParams.toString()
        });

        const twilioData = await twilioResp.json();
        if (twilioResp.ok) {
          return sendJson(res, 200, {
            success: true,
            message: `Real SMS successfully sent to ${formattedTo} via Twilio!`,
            provider: 'twilio',
            recipient: formattedTo,
            sid: twilioData.sid
          });
        } else {
          return sendJson(res, 400, {
            success: false,
            error: twilioData.message || 'Twilio delivery failed.'
          });
        }
      }

      return sendJson(res, 400, { success: false, error: `Unsupported SMS provider: ${provider}` });
    } catch (err) {
      console.error('SMS send error:', err);
      return sendJson(res, 500, { success: false, error: err.message });
    }
  }

  // ==========================================
  // STATIC FILES (FRONTEND HTML / ASSETS)
  // ==========================================
  let reqPath = decodeURI(pathname);
  if (reqPath === '/' || reqPath === '') {
    reqPath = '/index.html';
  }

  const filePath = path.join(BASE_DIR, reqPath);
  const ext = path.extname(filePath).toLowerCase();
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, content) => {
    if (err) {
      if (err.code === 'ENOENT') {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('404 Not Found');
      } else {
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        res.end('Server Error: ' + err.code);
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content);
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Frontend Web Server running at http://localhost:${PORT}/`);
  console.log(`Live Email API active via Resend!`);
  console.log(`Live SMS API active via Fast2SMS & Twilio!`);
});
