import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  // আপনার সার্ভার লাইভ হলে সেই URL টি এখানে বসাতে হবে
  static const String baseUrl = "https://your-server-url.com"; 

  // ১. ইউজারের ব্যালেন্স এবং প্রোফাইল ডাটা আনা
  static Future<Map<String, dynamic>> getUserStats(String userId) async {
    final response = await http.get(Uri.parse('$baseUrl/admin/stats'));
    
    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('ডাটা লোড করতে সমস্যা হচ্ছে');
    }
  }

  // ২. উইথড্রয়াল রিকোয়েস্ট পাঠানো
  static Future<bool> sendWithdrawRequest(String userId, double amount) async {
    final response = await http.post(
      Uri.parse('$baseUrl/admin/approve_withdraw'),
      headers: {"Content-Type": "application/json"},
      body: json.encode({
        "id": userId,
        "amount": amount,
      }),
    );

    return response.statusCode == 200;
  }

  // ৩. ট্রেডিং চার্টের লাইভ ডাটা আনা (AAF Coin Price)
  static Future<List<dynamic>> getChartData() async {
    final response = await http.get(Uri.parse('$baseUrl/trading/chart_data'));

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      return [];
    }
  }
}
