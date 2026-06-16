// test_fpm.cpp — Stage 4: chạy CFastMatch trên ảnh thật (Test Images/Src1+Dst1),
// so sánh nhánh SIMD on vs off. PASS nếu cả 2 đều match và top result trùng nhau.
#include "fpm_core.h"
#include <opencv2/imgcodecs.hpp>
#include <cstdio>

using namespace fpm;
using cv::Mat;

static void run (bool bSIMD, const Mat& src, const Mat& templ, std::vector<s_SingleTargetMatch>& out)
{
	MatchParams params;
	params.bUseSIMD = bSIMD;
	CFastMatch matcher;
	matcher.LearnPattern (templ, params);
	out = matcher.Match (src, params);
}

int main (int argc, char** argv)
{
	const char* srcPath = argc > 1 ? argv[1] : "Test Images/Src1.bmp";
	const char* dstPath = argc > 2 ? argv[2] : "Test Images/Dst1.bmp";

	Mat src = cv::imread (srcPath, cv::IMREAD_GRAYSCALE);
	Mat templ = cv::imread (dstPath, cv::IMREAD_GRAYSCALE);
	if (src.empty () || templ.empty ())
	{
		printf ("Cannot load images: %s / %s\nSTAGE4 FAIL\n", srcPath, dstPath);
		return 2;
	}
	printf ("src=%dx%d templ=%dx%d\n", src.cols, src.rows, templ.cols, templ.rows);

	std::vector<s_SingleTargetMatch> r0, r1;
	run (false, src, templ, r0);
	run (true, src, templ, r1);

	auto dump = [] (const char* tag, const std::vector<s_SingleTargetMatch>& r) {
		printf ("[%s] matches=%zu", tag, r.size ());
		if (!r.empty ())
			printf ("  top: center=(%.2f,%.2f) angle=%.2f score=%.4f", r[0].ptCenter.x, r[0].ptCenter.y, r[0].dMatchedAngle, r[0].dMatchScore);
		printf ("\n");
	};
	dump ("SIMD=0", r0);
	dump ("SIMD=1", r1);

	int rc = 0;
	if (r0.empty () || r1.empty ()) { printf ("[FAIL] một nhánh không match\n"); rc = 1; }
	else
	{
		double dc = cv::norm (r0[0].ptCenter - r1[0].ptCenter);
		double da = std::abs (r0[0].dMatchedAngle - r1[0].dMatchedAngle);
		printf ("diff top: dCenter=%.3f px, dAngle=%.3f deg\n", dc, da);
		if (dc > 2.0 || da > 1.0) { printf ("[FAIL] 2 nhánh SIMD lệch nhau\n"); rc = 1; }
	}
	printf (rc == 0 ? "STAGE4 PASS\n" : "STAGE4 FAIL\n");
	return rc;
}
