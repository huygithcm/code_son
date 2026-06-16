// fpm_core.h — lõi thuật toán Fastest Image Pattern Matching, tách khỏi MFC.
// Chỉ phụ thuộc OpenCV + STL. Không include afx*/windows.
#pragma once

#include <opencv2/opencv.hpp>
#ifndef OPENCV_4X
#define OPENCV_4X
#endif
#include <opencv2/highgui/highgui_c.h>
#include <opencv2/imgproc/imgproc_c.h>
#include <opencv2/imgproc/types_c.h>

#include <vector>
#include <utility>

namespace fpm {

using cv::Mat;
using cv::Point;
using cv::Point2d;
using cv::Point2f;
using cv::Rect;
using cv::RotatedRect;
using cv::Scalar;
using cv::Size;
using std::vector;

// ---- Hằng số (port từ MatchToolDlg.cpp) ----
constexpr double VISION_TOLERANCE = 0.0000001;
constexpr double D2R = CV_PI / 180.0;
constexpr double R2D = 180.0 / CV_PI;
constexpr int    MATCH_CANDIDATE_NUM = 5;

// ================= Tham số match (gom từ dialog GUI) =================
// Default đặt đúng theo CMatchToolDlg constructor / DoDataExchange.
struct MatchParams
{
	int    iMaxPos         = 70;     // số target tối đa            (m_iMaxPos)
	double dMaxOverlap     = 0.0;    // tỉ lệ chồng lấp tối đa      (m_dMaxOverlap)
	double dScore          = 0.5;    // ngưỡng score                (m_dScore)
	double dToleranceAngle = 0.0;    // dung sai góc                (m_dToleranceAngle)
	int    iMinReduceArea  = 256;    // diện tích nhỏ nhất pyramid  (m_iMinReduceArea)

	bool   bToleranceRange = false;  // dùng dải góc [t1,t2]&[t3,t4](m_bToleranceRange)
	double dTolerance1     = 40.0;   // (m_dTolerance1)
	double dTolerance2     = 60.0;   // (m_dTolerance2)
	double dTolerance3     = -110.0; // (m_dTolerance3)
	double dTolerance4     = -100.0; // (m_dTolerance4)

	bool   bStopLayer1     = false;  // FastMode: dừng ở layer 1    (m_bStopLayer1)
	bool   bBitwiseNot     = false;  // đảo ảnh nguồn (255-src)     (m_ckBitwiseNot)
	bool   bUseSIMD        = true;   // bật SIMD ở refine layer     (m_ckSIMD)
	bool   bSubPixel       = false;  // ước lượng subpixel          (m_bSubPixel)
};

// ================= Struct dữ liệu (BOOL->bool) =================
struct s_TemplData
{
	vector<Mat>    vecPyramid;
	vector<Scalar> vecTemplMean;
	vector<double> vecTemplNorm;
	vector<double> vecInvArea;
	vector<bool>   vecResultEqual1;
	bool           bIsPatternLearned;
	int            iBorderColor;

	void clear ()
	{
		vector<Mat> ().swap (vecPyramid);
		vector<double> ().swap (vecTemplNorm);
		vector<double> ().swap (vecInvArea);
		vector<Scalar> ().swap (vecTemplMean);
		vector<bool> ().swap (vecResultEqual1);
	}
	void resize (int iSize)
	{
		vecTemplMean.resize (iSize);
		vecTemplNorm.resize (iSize, 0);
		vecInvArea.resize (iSize, 1);
		vecResultEqual1.resize (iSize, false);
	}
	s_TemplData () { bIsPatternLearned = false; }
};

struct s_MatchParameter
{
	Point2d     pt;
	double      dMatchScore;
	double      dMatchAngle;
	Rect        rectRoi;
	double      dAngleStart;
	double      dAngleEnd;
	RotatedRect rectR;
	Rect        rectBounding;
	bool        bDelete;

	double      vecResult[3][3]; // for subpixel
	int         iMaxScoreIndex;  // for subpixel
	bool        bPosOnBorder;
	Point2d     ptSubPixel;
	double      dNewAngle;

	s_MatchParameter (Point2f ptMinMax, double dScore, double dAngle)
	{
		pt = ptMinMax;
		dMatchScore = dScore;
		dMatchAngle = dAngle;
		bDelete = false;
		dNewAngle = 0.0;
		bPosOnBorder = false;
	}
	s_MatchParameter ()
	{
		dMatchScore = 0;
		dMatchAngle = 0;
	}
	~s_MatchParameter () {}
};

struct s_SingleTargetMatch
{
	Point2d ptLT, ptRT, ptRB, ptLB, ptCenter;
	double  dMatchedAngle;
	double  dMatchScore;
};

struct s_BlockMax
{
	struct Block
	{
		Rect   rect;
		double dMax;
		Point  ptMaxLoc;
		Block () {}
		Block (Rect rect_, double dMax_, Point ptMaxLoc_)
			: rect (rect_), dMax (dMax_), ptMaxLoc (ptMaxLoc_) {}
	};
	s_BlockMax () {}
	vector<Block> vecBlock;
	Mat           matSrc;

	s_BlockMax (Mat matSrc_, Size sizeTemplate);
	void UpdateMax (Rect rectIgnore);
	void GetMaxValueLoc (double& dMax, Point& ptMaxLoc);
};

// ================= Comparator =================
bool compareScoreBig2Small (const s_MatchParameter& lhs, const s_MatchParameter& rhs);
bool comparePtWithAngle (const std::pair<Point2f, double> lhs, const std::pair<Point2f, double> rhs);

// ================= Hàm lõi thuần (Stage 1) =================
int     GetTopLayer (Mat* matTempl, int iMinDstLength);
void    MatchTemplate (Mat& matSrc, s_TemplData* pTemplData, Mat& matResult, int iLayer, bool bUseSIMD);
void    GetRotatedROI (Mat& matSrc, Size size, Point2f ptLT, double dAngle, Mat& matROI);
void    CCOEFF_Denominator (Mat& matSrc, s_TemplData* pTemplData, Mat& matResult, int iLayer);
Size    GetBestRotationSize (Size sizeSrc, Size sizeDst, double dRAngle);
Point2f ptRotatePt2f (Point2f ptInput, Point2f ptOrg, double dAngle);
void    FilterWithScore (vector<s_MatchParameter>* vec, double dScore);
void    FilterWithRotatedRect (vector<s_MatchParameter>* vec, int iMethod, double dMaxOverLap);
Point   GetNextMaxLoc (Mat& matResult, Point ptMaxLoc, Size sizeTemplate, double& dMaxValue, double dMaxOverlap);
Point   GetNextMaxLoc (Mat& matResult, Point ptMaxLoc, Size sizeTemplate, double& dMaxValue, double dMaxOverlap, s_BlockMax& blockMax);
void    SortPtWithCenter (vector<Point2f>& vecSort);
bool    SubPixEsimation (vector<s_MatchParameter>* vec, double* dNewX, double* dNewY, double* dNewAngle, double dAngleStep, int iMaxScoreIndex);
void    DrawDashLine (Mat& matDraw, Point ptStart, Point ptEnd, Scalar color1 = Scalar (0, 0, 255), Scalar color2 = Scalar::all (255));
void    DrawMarkCross (Mat& matDraw, int iX, int iY, int iLength, Scalar color, int iThickness);

// ================= Class lõi (Stage 3) — không MFC =================
// Port từ CMatchToolDlg::LearnPattern + Match, bỏ toàn bộ GUI.
// Ảnh vào: 8UC1 (nếu nhiều kênh sẽ tự cvtColor sang gray).
class CFastMatch
{
public:
	// Học template (tương đương LearnPattern). matTemplate: ảnh mẫu.
	void LearnPattern (const Mat& matTemplate, const MatchParams& params);

	// Tìm template trong matSource. Trả danh sách target (đã sắp theo score giảm dần).
	// Throw std::invalid_argument nếu tham số/ảnh không hợp lệ; trả vector rỗng nếu không match.
	vector<s_SingleTargetMatch> Match (const Mat& matSource, const MatchParams& params);

	bool IsPatternLearned () const { return m_TemplData.bIsPatternLearned; }

private:
	s_TemplData m_TemplData;  // pyramid + thống kê template
	Mat         m_matTempl;   // template gray (layer 0), cho size-check & GetTopLayer
};

} // namespace fpm
