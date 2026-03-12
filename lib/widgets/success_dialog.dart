import 'package:flutter/material.dart';
import 'package:lottie/lottie.dart';

class SuccessDialog extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      backgroundColor: Color(0xFF1E1E1E), // ডার্ক থিম
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // টাকার বৃষ্টির বা সাকসেস অ্যানিমেশন
            Lottie.network(
              'https://assets10.lottiefiles.com/packages/lf20_pqnfmone.json',
              repeat: false,
              height: 150,
            ),
            SizedBox(height: 20),
            Text(
              "পেমেন্ট সফল হয়েছে!",
              style: TextStyle(
                color: Colors.greenAccent, 
                fontSize: 20, 
                fontWeight: FontWeight.bold
              ),
            ),
            SizedBox(height: 10),
            Text(
              "আপনার টাকা আপনার ওয়ালেটে পাঠিয়ে দেওয়া হয়েছে।",
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white70),
            ),
            SizedBox(height: 20),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.redAccent,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))
              ),
              onPressed: () => Navigator.pop(context),
              child: Text("ঠিক আছে", style: TextStyle(color: Colors.white)),
            )
          ],
        ),
      ),
    );
  }
}
