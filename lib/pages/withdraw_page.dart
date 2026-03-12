import 'package:flutter/material.dart';

class WithdrawPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Color(0xFF121212),
      appBar: AppBar(title: Text("Withdraw Money"), backgroundColor: Colors.redAccent),
      body: Padding(
        padding: EdgeInsets.all(20),
        child: Column(
          children: [
            TextField(
              decoration: InputDecoration(
                labelText: "বিকাশ/নগদ নম্বর দিন",
                labelStyle: TextStyle(color: Colors.white70),
                enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.redAccent)),
              ),
              style: TextStyle(color: Colors.white),
              keyboardType: TextInputType.phone,
            ),
            SizedBox(height: 20),
            ElevatedButton(
              onPressed: () {
                // এখানে ক্লিক করলে রিকোয়েস্ট এডমিন প্যানেলে যাবে
              },
              child: Text("উইথড্র রিকোয়েস্ট পাঠান"),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
            )
          ],
        ),
      ),
    );
  }
}
