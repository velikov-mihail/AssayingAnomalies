function [FF17, FF17Names] = makeFF17Indus(SIC) 
% PURPOSE: This function creates a Fama and French 17-industry
% classification index and a table with the industry names
%------------------------------------------------------------------------------------------
% USAGE:   
% [FF17, FF17Names] = makeFF49Indus(SIC)          
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -SIC - a matrix containing SIC codes
%------------------------------------------------------------------------------------------
% Output:
%        -inds - matrix with the industries indicators
%        -FF17Names - table with the industry names
%------------------------------------------------------------------------------------------
% Examples:
%
% [FF17, FF17Names] = makeFF49Indus(SIC)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

%  1 Food   Food
indus = (SIC >= 	100	 & SIC <= 	199	);
indus = indus + (SIC >=	200	 & SIC <= 	299	);
indus = indus + (SIC >=	700	 & SIC <= 	799	);
indus = indus + (SIC >=	900	 & SIC <= 	999	);
indus = indus + (SIC >=	2000	 & SIC <= 	2009	);
indus = indus + (SIC >=	2010	 & SIC <= 	2019	);
indus = indus + (SIC >=	2020	 & SIC <= 	2029	);
indus = indus + (SIC >=	2030	 & SIC <= 	2039	);
indus = indus + (SIC >=	2040	 & SIC <= 	2046	);
indus = indus + (SIC >=	2047	 & SIC <= 	2047	);
indus = indus + (SIC >=	2048	 & SIC <= 	2048	);
indus = indus + (SIC >=	2050	 & SIC <= 	2059	);
indus = indus + (SIC >=	2060	 & SIC <= 	2063	);
indus = indus + (SIC >=	2064	 & SIC <= 	2068	);
indus = indus + (SIC >=	2070	 & SIC <= 	2079	);
indus = indus + (SIC >=	2080	 & SIC <= 	2080	);
indus = indus + (SIC >=	2082	 & SIC <= 	2082	);
indus = indus + (SIC >=	2083	 & SIC <= 	2083	);
indus = indus + (SIC >=	2084	 & SIC <= 	2084	);
indus = indus + (SIC >=	2085	 & SIC <= 	2085	);
indus = indus + (SIC >=	2086	 & SIC <= 	2086	);
indus = indus + (SIC >=	2087	 & SIC <= 	2087	);
indus = indus + (SIC >=	2090	 & SIC <= 	2092	);
indus = indus + (SIC >=	2095	 & SIC <= 	2095	);
indus = indus + (SIC >=	2096	 & SIC <= 	2096	);
indus = indus + (SIC >=	2097	 & SIC <= 	2097	);
indus = indus + (SIC >=	2098	 & SIC <= 	2099	);
indus = indus + (SIC >=	5140	 & SIC <= 	5149	);
indus = indus + (SIC >=	5150	 & SIC <= 	5159	);
indus = indus + (SIC >=	5180	 & SIC <= 	5182	);
indus = indus + (SIC >=	5191	 & SIC <= 	5191	);


%  2 Mines  Mining and Minerals
indus = indus + 2*(SIC >=	1000	 & SIC <= 	1009	);
indus = indus + 2*(SIC >=	1010	 & SIC <= 	1019	);
indus = indus + 2*(SIC >=	1020	 & SIC <= 	1029	);
indus = indus + 2*(SIC >=	1030	 & SIC <= 	1039	);
indus = indus + 2*(SIC >=	1040	 & SIC <= 	1049	);
indus = indus + 2*(SIC >=	1060	 & SIC <= 	1069	);
indus = indus + 2*(SIC >=	1080	 & SIC <= 	1089	);
indus = indus + 2*(SIC >=	1090	 & SIC <= 	1099	);
indus = indus + 2*(SIC >=	1200	 & SIC <= 	1299	);
indus = indus + 2*(SIC >=	1400	 & SIC <= 	1499	);
indus = indus + 2*(SIC >=	5050	 & SIC <= 	5052	);

% 	 3 Oil    Oil and Petroleum Products			);
indus = indus + 3*(SIC >=	1300	 & SIC <= 	1300	);
indus = indus + 3*(SIC >=	1310	 & SIC <= 	1319	);
indus = indus + 3*(SIC >=	1320	 & SIC <= 	1329	);
indus = indus + 3*(SIC >=	1380	 & SIC <= 	1380	);
indus = indus + 3*(SIC >=	1381	 & SIC <= 	1381	);
indus = indus + 3*(SIC >=	1382	 & SIC <= 	1382	);
indus = indus + 3*(SIC >=	1389	 & SIC <= 	1389	);
indus = indus + 3*(SIC >=	2900	 & SIC <= 	2912	);
indus = indus + 3*(SIC >=	5170	 & SIC <= 	5172	);
				
% 	 4 Clths  Textiles, Apparel & Footware			);
indus = indus + 4*(SIC >=	2200	 & SIC <= 	2269	);
indus = indus + 4*(SIC >=	2270	 & SIC <= 	2279	);
indus = indus + 4*(SIC >=	2280	 & SIC <= 	2284	);
indus = indus + 4*(SIC >=	2290	 & SIC <= 	2295	);
indus = indus + 4*(SIC >=	2296	 & SIC <= 	2296	);
indus = indus + 4*(SIC >=	2297	 & SIC <= 	2297	);
indus = indus + 4*(SIC >=	2298	 & SIC <= 	2298	);
indus = indus + 4*(SIC >=	2299	 & SIC <= 	2299	);
indus = indus + 4*(SIC >=	2300	 & SIC <= 	2390	);
indus = indus + 4*(SIC >=	2391	 & SIC <= 	2392	);
indus = indus + 4*(SIC >=	2393	 & SIC <= 	2395	);
indus = indus + 4*(SIC >=	2396	 & SIC <= 	2396	);
indus = indus + 4*(SIC >=	2397	 & SIC <= 	2399	);
indus = indus + 4*(SIC >=	3020	 & SIC <= 	3021	);
indus = indus + 4*(SIC >=	3100	 & SIC <= 	3111	);
indus = indus + 4*(SIC >=	3130	 & SIC <= 	3131	);
indus = indus + 4*(SIC >=	3140	 & SIC <= 	3149	);
indus = indus + 4*(SIC >=	3150	 & SIC <= 	3151	);
indus = indus + 4*(SIC >=	3963	 & SIC <= 	3965	);
indus = indus + 4*(SIC >=	5130	 & SIC <= 	5139	);
				
% 	 5 Durbl  Consumer Durables			);
indus = indus + 5*(SIC >=	2510	 & SIC <= 	2519	);
indus = indus + 5*(SIC >=	2590	 & SIC <= 	2599	);
indus = indus + 5*(SIC >=	3060	 & SIC <= 	3069	);
indus = indus + 5*(SIC >=	3070	 & SIC <= 	3079	);
indus = indus + 5*(SIC >=	3080	 & SIC <= 	3089	);
indus = indus + 5*(SIC >=	3090	 & SIC <= 	3099	);
indus = indus + 5*(SIC >=	3630	 & SIC <= 	3639	);
indus = indus + 5*(SIC >=	3650	 & SIC <= 	3651	);
indus = indus + 5*(SIC >=	3652	 & SIC <= 	3652	);
indus = indus + 5*(SIC >=	3860	 & SIC <= 	3861	);
indus = indus + 5*(SIC >=	3870	 & SIC <= 	3873	);
indus = indus + 5*(SIC >=	3910	 & SIC <= 	3911	);
indus = indus + 5*(SIC >=	3914	 & SIC <= 	3914	);
indus = indus + 5*(SIC >=	3915	 & SIC <= 	3915	);
indus = indus + 5*(SIC >=	3930	 & SIC <= 	3931	);
indus = indus + 5*(SIC >=	3940	 & SIC <= 	3949	);
indus = indus + 5*(SIC >=	3960	 & SIC <= 	3962	);
indus = indus + 5*(SIC >=	5020	 & SIC <= 	5023	);
indus = indus + 5*(SIC >=	5064	 & SIC <= 	5064	);
indus = indus + 5*(SIC >=	5094	 & SIC <= 	5094	);
indus = indus + 5*(SIC >=	5099	 & SIC <= 	5099	);
			
% 	 6 Chems  Chemicals			);
indus = indus + 6*(SIC >=	2800	 & SIC <= 	2809	);
indus = indus + 6*(SIC >=	2810	 & SIC <= 	2819	);
indus = indus + 6*(SIC >=	2820	 & SIC <= 	2829	);
indus = indus + 6*(SIC >=	2860	 & SIC <= 	2869	);
indus = indus + 6*(SIC >=	2870	 & SIC <= 	2879	);
indus = indus + 6*(SIC >=	2890	 & SIC <= 	2899	);
indus = indus + 6*(SIC >=	5160	 & SIC <= 	5169	);
				
% 	 7 Cnsum  Drugs, Soap, Prfums, Tobacco			);
indus = indus +7*(SIC >=	2100	 & SIC <= 	2199	);
indus = indus +7*(SIC >=	2830	 & SIC <= 	2830	);
indus = indus +7*(SIC >=	2831	 & SIC <= 	2831	);
indus = indus +7*(SIC >=	2833	 & SIC <= 	2833	);
indus = indus +7*(SIC >=	2834	 & SIC <= 	2834	);
indus = indus +7*(SIC >=	2840	 & SIC <= 	2843	);
indus = indus +7*(SIC >=	2844	 & SIC <= 	2844	);
indus = indus +7*(SIC >=	5120	 & SIC <= 	5122	);
indus = indus +7*(SIC >=	5194	 & SIC <= 	5194	);
		
% 	 8 Cnstr  Construction and Construction Materials			);
indus = indus +8*(SIC >=	800	 & SIC <= 	899	);
indus = indus +8*(SIC >=	1500	 & SIC <= 	1511	);
indus = indus +8*(SIC >=	1520	 & SIC <= 	1529	);
indus = indus +8*(SIC >=	1530	 & SIC <= 	1539	);
indus = indus +8*(SIC >=	1540	 & SIC <= 	1549	);
indus = indus +8*(SIC >=	1600	 & SIC <= 	1699	);
indus = indus +8*(SIC >=	1700	 & SIC <= 	1799	);
indus = indus +8*(SIC >=	2400	 & SIC <= 	2439	);
indus = indus +8*(SIC >=	2440	 & SIC <= 	2449	);
indus = indus +8*(SIC >=	2450	 & SIC <= 	2459	);
indus = indus +8*(SIC >=	2490	 & SIC <= 	2499	);
indus = indus +8*(SIC >=	2850	 & SIC <= 	2859	);
indus = indus +8*(SIC >=	2950	 & SIC <= 	2952	);
indus = indus +8*(SIC >=	3200	 & SIC <= 	3200	);
indus = indus +8*(SIC >=	3210	 & SIC <= 	3211	);
indus = indus +8*(SIC >=	3240	 & SIC <= 	3241	);
indus = indus +8*(SIC >=	3250	 & SIC <= 	3259	);
indus = indus +8*(SIC >=	3261	 & SIC <= 	3261	);
indus = indus +8*(SIC >=	3264	 & SIC <= 	3264	);
indus = indus +8*(SIC >=	3270	 & SIC <= 	3275	);
indus = indus +8*(SIC >=	3280	 & SIC <= 	3281	);
indus = indus +8*(SIC >=	3290	 & SIC <= 	3293	);
indus = indus +8*(SIC >=	3420	 & SIC <= 	3429	);
indus = indus +8*(SIC >=	3430	 & SIC <= 	3433	);
indus = indus +8*(SIC >=	3440	 & SIC <= 	3441	);
indus = indus +8*(SIC >=	3442	 & SIC <= 	3442	);
indus = indus +8*(SIC >=	3446	 & SIC <= 	3446	);
indus = indus +8*(SIC >=	3448	 & SIC <= 	3448	);
indus = indus +8*(SIC >=	3449	 & SIC <= 	3449	);
indus = indus +8*(SIC >=	3450	 & SIC <= 	3451	);
indus = indus +8*(SIC >=	3452	 & SIC <= 	3452	);
indus = indus +8*(SIC >=	5030	 & SIC <= 	5039	);
indus = indus +8*(SIC >=	5070	 & SIC <= 	5078	);
indus = indus +8*(SIC >=	5198	 & SIC <= 	5198	);
indus = indus +8*(SIC >=	5210	 & SIC <= 	5211	);
indus = indus +8*(SIC >=	5230	 & SIC <= 	5231	);
indus = indus +8*(SIC >=	5250	 & SIC <= 	5251	);
	
% 	 9 Steel  Steel Works Etc	 & SIC <= 		);
indus = indus +9*(SIC >=	3300	 & SIC <= 	3300	);
indus = indus +9*(SIC >=	3310	 & SIC <= 	3317	);
indus = indus +9*(SIC >=	3320	 & SIC <= 	3325	);
indus = indus +9*(SIC >=	3330	 & SIC <= 	3339	);
indus = indus +9*(SIC >=	3340	 & SIC <= 	3341	);
indus = indus +9*(SIC >=	3350	 & SIC <= 	3357	);
indus = indus +9*(SIC >=	3360	 & SIC <= 	3369	);
indus = indus +9*(SIC >=	3390	 & SIC <= 	3399	);
	
% 	10 FabPr  Fabricated Products	 & SIC <= 		);
indus = indus +10*(SIC >=	3410	 & SIC <= 	3412	);
indus = indus +10*(SIC >=	3443	 & SIC <= 	3443	);
indus = indus +10*(SIC >=	3444	 & SIC <= 	3444	);
indus = indus +10*(SIC >=	3460	 & SIC <= 	3469	);
indus = indus +10*(SIC >=	3470	 & SIC <= 	3479	);
indus = indus +10*(SIC >=	3480	 & SIC <= 	3489	);
indus = indus +10*(SIC >=	3490	 & SIC <= 	3499	);

% 	11 Machn  Machinery and Business Equipment	 & SIC <= 		);
indus = indus +11*(SIC >=	3510	 & SIC <= 	3519	);
indus = indus +11*(SIC >=	3520	 & SIC <= 	3529	);
indus = indus +11*(SIC >=	3530	 & SIC <= 	3530	);
indus = indus +11*(SIC >=	3531	 & SIC <= 	3531	);
indus = indus +11*(SIC >=	3532	 & SIC <= 	3532	);
indus = indus +11*(SIC >=	3533	 & SIC <= 	3533	);
indus = indus +11*(SIC >=	3534	 & SIC <= 	3534	);
indus = indus +11*(SIC >=	3535	 & SIC <= 	3535	);
indus = indus +11*(SIC >=	3536	 & SIC <= 	3536	);
indus = indus +11*(SIC >=	3540	 & SIC <= 	3549	);
indus = indus +11*(SIC >=	3550	 & SIC <= 	3559	);
indus = indus +11*(SIC >=	3560	 & SIC <= 	3569	);
indus = indus +11*(SIC >=	3570	 & SIC <= 	3579	);
indus = indus +11*(SIC >=	3580	 & SIC <= 	3580	);
indus = indus +11*(SIC >=	3581	 & SIC <= 	3581	);
indus = indus +11*(SIC >=	3582	 & SIC <= 	3582	);
indus = indus +11*(SIC >=	3585	 & SIC <= 	3585	);
indus = indus +11*(SIC >=	3586	 & SIC <= 	3586	);
indus = indus +11*(SIC >=	3589	 & SIC <= 	3589	);
indus = indus +11*(SIC >=	3590	 & SIC <= 	3599	);
indus = indus +11*(SIC >=	3600	 & SIC <= 	3600	);
indus = indus +11*(SIC >=	3610	 & SIC <= 	3613	);
indus = indus +11*(SIC >=	3620	 & SIC <= 	3621	);
indus = indus +11*(SIC >=	3622	 & SIC <= 	3622	);
indus = indus +11*(SIC >=	3623	 & SIC <= 	3629	);
indus = indus +11*(SIC >=	3670	 & SIC <= 	3679	);
indus = indus +11*(SIC >=	3680	 & SIC <= 	3680	);
indus = indus +11*(SIC >=	3681	 & SIC <= 	3681	);
indus = indus +11*(SIC >=	3682	 & SIC <= 	3682	);
indus = indus +11*(SIC >=	3683	 & SIC <= 	3683	);
indus = indus +11*(SIC >=	3684	 & SIC <= 	3684	);
indus = indus +11*(SIC >=	3685	 & SIC <= 	3685	);
indus = indus +11*(SIC >=	3686	 & SIC <= 	3686	);
indus = indus +11*(SIC >=	3687	 & SIC <= 	3687	);
indus = indus +11*(SIC >=	3688	 & SIC <= 	3688	);
indus = indus +11*(SIC >=	3689	 & SIC <= 	3689	);
indus = indus +11*(SIC >=	3690	 & SIC <= 	3690	);
indus = indus +11*(SIC >=	3691	 & SIC <= 	3692	);
indus = indus +11*(SIC >=	3693	 & SIC <= 	3693	);
indus = indus +11*(SIC >=	3694	 & SIC <= 	3694	);
indus = indus +11*(SIC >=	3695	 & SIC <= 	3695	);
indus = indus +11*(SIC >=	3699	 & SIC <= 	3699	);
indus = indus +11*(SIC >=	3810	 & SIC <= 	3810	);
indus = indus +11*(SIC >=	3811	 & SIC <= 	3811	);
indus = indus +11*(SIC >=	3812	 & SIC <= 	3812	);
indus = indus +11*(SIC >=	3820	 & SIC <= 	3820	);
indus = indus +11*(SIC >=	3821	 & SIC <= 	3821	);
indus = indus +11*(SIC >=	3822	 & SIC <= 	3822	);
indus = indus +11*(SIC >=	3823	 & SIC <= 	3823	);
indus = indus +11*(SIC >=	3824	 & SIC <= 	3824	);
indus = indus +11*(SIC >=	3825	 & SIC <= 	3825	);
indus = indus +11*(SIC >=	3826	 & SIC <= 	3826	);
indus = indus +11*(SIC >=	3827	 & SIC <= 	3827	);
indus = indus +11*(SIC >=	3829	 & SIC <= 	3829	);
indus = indus +11*(SIC >=	3830	 & SIC <= 	3839	);
indus = indus +11*(SIC >=	3950	 & SIC <= 	3955	);
indus = indus +11*(SIC >=	5060	 & SIC <= 	5060	);
indus = indus +11*(SIC >=	5063	 & SIC <= 	5063	);
indus = indus +11*(SIC >=	5065	 & SIC <= 	5065	);
indus = indus +11*(SIC >=	5080	 & SIC <= 	5080	);
indus = indus +11*(SIC >=	5081	 & SIC <= 	5081	);
		
% 	12 Cars   Automobiles	 & SIC <= 		);
indus = indus +12*(SIC >=	3710	 & SIC <= 	3710	);
indus = indus +12*(SIC >=	3711	 & SIC <= 	3711	);
indus = indus +12*(SIC >=	3714	 & SIC <= 	3714	);
indus = indus +12*(SIC >=	3716	 & SIC <= 	3716	);
indus = indus +12*(SIC >=	3750	 & SIC <= 	3751	);
indus = indus +12*(SIC >=	3792	 & SIC <= 	3792	);
indus = indus +12*(SIC >=	5010	 & SIC <= 	5015	);
indus = indus +12*(SIC >=	5510	 & SIC <= 	5521	);
indus = indus +12*(SIC >=	5530	 & SIC <= 	5531	);
indus = indus +12*(SIC >=	5560	 & SIC <= 	5561	);
indus = indus +12*(SIC >=	5570	 & SIC <= 	5571	);
indus = indus +12*(SIC >=	5590	 & SIC <= 	5599	);
	
% 	13 Trans  Transportation	 & SIC <= 		);
indus = indus +13*(SIC >=	3713	 & SIC <= 	3713	);
indus = indus +13*(SIC >=	3715	 & SIC <= 	3715	);
indus = indus +13*(SIC >=	3720	 & SIC <= 	3720	);
indus = indus +13*(SIC >=	3721	 & SIC <= 	3721	);
indus = indus +13*(SIC >=	3724	 & SIC <= 	3724	);
indus = indus +13*(SIC >=	3725	 & SIC <= 	3725	);
indus = indus +13*(SIC >=	3728	 & SIC <= 	3728	);
indus = indus +13*(SIC >=	3730	 & SIC <= 	3731	);
indus = indus +13*(SIC >=	3732	 & SIC <= 	3732	);
indus = indus +13*(SIC >=	3740	 & SIC <= 	3743	);
indus = indus +13*(SIC >=	3760	 & SIC <= 	3769	);
indus = indus +13*(SIC >=	3790	 & SIC <= 	3790	);
indus = indus +13*(SIC >=	3795	 & SIC <= 	3795	);
indus = indus +13*(SIC >=	3799	 & SIC <= 	3799	);
indus = indus +13*(SIC >=	4000	 & SIC <= 	4013	);
indus = indus +13*(SIC >=	4100	 & SIC <= 	4100	);
indus = indus +13*(SIC >=	4110	 & SIC <= 	4119	);
indus = indus +13*(SIC >=	4120	 & SIC <= 	4121	);
indus = indus +13*(SIC >=	4130	 & SIC <= 	4131	);
indus = indus +13*(SIC >=	4140	 & SIC <= 	4142	);
indus = indus +13*(SIC >=	4150	 & SIC <= 	4151	);
indus = indus +13*(SIC >=	4170	 & SIC <= 	4173	);
indus = indus +13*(SIC >=	4190	 & SIC <= 	4199	);
indus = indus +13*(SIC >=	4200	 & SIC <= 	4200	);
indus = indus +13*(SIC >=	4210	 & SIC <= 	4219	);
indus = indus +13*(SIC >=	4220	 & SIC <= 	4229	);
indus = indus +13*(SIC >=	4230	 & SIC <= 	4231	);
indus = indus +13*(SIC >=	4400	 & SIC <= 	4499	);
indus = indus +13*(SIC >=	4500	 & SIC <= 	4599	);
indus = indus +13*(SIC >=	4600	 & SIC <= 	4699	);
indus = indus +13*(SIC >=	4700	 & SIC <= 	4700	);
indus = indus +13*(SIC >=	4710	 & SIC <= 	4712	);
indus = indus +13*(SIC >=	4720	 & SIC <= 	4729	);
indus = indus +13*(SIC >=	4730	 & SIC <= 	4739	);
indus = indus +13*(SIC >=	4740	 & SIC <= 	4742	);
indus = indus +13*(SIC >=	4780	 & SIC <= 	4780	);
indus = indus +13*(SIC >=	4783	 & SIC <= 	4783	);
indus = indus +13*(SIC >=	4785	 & SIC <= 	4785	);
indus = indus +13*(SIC >=	4789	 & SIC <= 	4789	);
		
% 	14 Utils  Utilities	 & SIC <= 		);
indus = indus +14*(SIC >=	4900	 & SIC <= 	4900	);
indus = indus +14*(SIC >=	4910	 & SIC <= 	4911	);
indus = indus +14*(SIC >=	4920	 & SIC <= 	4922	);
indus = indus +14*(SIC >=	4923	 & SIC <= 	4923	);
indus = indus +14*(SIC >=	4924	 & SIC <= 	4925	);
indus = indus +14*(SIC >=	4930	 & SIC <= 	4931	);
indus = indus +14*(SIC >=	4932	 & SIC <= 	4932	);
indus = indus +14*(SIC >=	4939	 & SIC <= 	4939	);
indus = indus +14*(SIC >=	4940	 & SIC <= 	4942	);
	
% 	15 Rtail  Retail Stores	 & SIC <= 		);
indus = indus +15*(SIC >=	5260	 & SIC <= 	5261	);
indus = indus +15*(SIC >=	5270	 & SIC <= 	5271	);
indus = indus +15*(SIC >=	5300	 & SIC <= 	5300	);
indus = indus +15*(SIC >=	5310	 & SIC <= 	5311	);
indus = indus +15*(SIC >=	5320	 & SIC <= 	5320	);
indus = indus +15*(SIC >=	5330	 & SIC <= 	5331	);
indus = indus +15*(SIC >=	5334	 & SIC <= 	5334	);
indus = indus +15*(SIC >=	5390	 & SIC <= 	5399	);
indus = indus +15*(SIC >=	5400	 & SIC <= 	5400	);
indus = indus +15*(SIC >=	5410	 & SIC <= 	5411	);
indus = indus +15*(SIC >=	5412	 & SIC <= 	5412	);
indus = indus +15*(SIC >=	5420	 & SIC <= 	5421	);
indus = indus +15*(SIC >=	5430	 & SIC <= 	5431	);
indus = indus +15*(SIC >=	5440	 & SIC <= 	5441	);
indus = indus +15*(SIC >=	5450	 & SIC <= 	5451	);
indus = indus +15*(SIC >=	5460	 & SIC <= 	5461	);
indus = indus +15*(SIC >=	5490	 & SIC <= 	5499	);
indus = indus +15*(SIC >=	5540	 & SIC <= 	5541	);
indus = indus +15*(SIC >=	5550	 & SIC <= 	5551	);
indus = indus +15*(SIC >=	5600	 & SIC <= 	5699	);
indus = indus +15*(SIC >=	5700	 & SIC <= 	5700	);
indus = indus +15*(SIC >=	5710	 & SIC <= 	5719	);
indus = indus +15*(SIC >=	5720	 & SIC <= 	5722	);
indus = indus +15*(SIC >=	5730	 & SIC <= 	5733	);
indus = indus +15*(SIC >=	5734	 & SIC <= 	5734	);
indus = indus +15*(SIC >=	5735	 & SIC <= 	5735	);
indus = indus +15*(SIC >=	5736	 & SIC <= 	5736	);
indus = indus +15*(SIC >=	5750	 & SIC <= 	5750	);
indus = indus +15*(SIC >=	5800	 & SIC <= 	5813	);
indus = indus +15*(SIC >=	5890	 & SIC <= 	5890	);
indus = indus +15*(SIC >=	5900	 & SIC <= 	5900	);
indus = indus +15*(SIC >=	5910	 & SIC <= 	5912	);
indus = indus +15*(SIC >=	5920	 & SIC <= 	5921	);
indus = indus +15*(SIC >=	5930	 & SIC <= 	5932	);
indus = indus +15*(SIC >=	5940	 & SIC <= 	5940	);
indus = indus +15*(SIC >=	5941	 & SIC <= 	5941	);
indus = indus +15*(SIC >=	5942	 & SIC <= 	5942	);
indus = indus +15*(SIC >=	5943	 & SIC <= 	5943	);
indus = indus +15*(SIC >=	5944	 & SIC <= 	5944	);
indus = indus +15*(SIC >=	5945	 & SIC <= 	5945	);
indus = indus +15*(SIC >=	5946	 & SIC <= 	5946	);
indus = indus +15*(SIC >=	5947	 & SIC <= 	5947	);
indus = indus +15*(SIC >=	5948	 & SIC <= 	5948	);
indus = indus +15*(SIC >=	5949	 & SIC <= 	5949	);
indus = indus +15*(SIC >=	5960	 & SIC <= 	5963	);
indus = indus +15*(SIC >=	5980	 & SIC <= 	5989	);
indus = indus +15*(SIC >=	5990	 & SIC <= 	5990	);
indus = indus +15*(SIC >=	5992	 & SIC <= 	5992	);
indus = indus +15*(SIC >=	5993	 & SIC <= 	5993	);
indus = indus +15*(SIC >=	5994	 & SIC <= 	5994	);
indus = indus +15*(SIC >=	5995	 & SIC <= 	5995	);
indus = indus +15*(SIC >=	5999	 & SIC <= 	5999	);
		 
% 	16 Finan  Banks, Insurance Companies, and Other Financials	 & SIC <= 		);
indus = indus +16*(SIC >=	6010	 & SIC <= 	6019	);
indus = indus +16*(SIC >=	6020	 & SIC <= 	6020	);
indus = indus +16*(SIC >=	6021	 & SIC <= 	6021	);
indus = indus +16*(SIC >=	6022	 & SIC <= 	6022	);
indus = indus +16*(SIC >=	6023	 & SIC <= 	6023	);
indus = indus +16*(SIC >=	6025	 & SIC <= 	6025	);
indus = indus +16*(SIC >=	6026	 & SIC <= 	6026	);
indus = indus +16*(SIC >=	6028	 & SIC <= 	6029	);
indus = indus +16*(SIC >=	6030	 & SIC <= 	6036	);
indus = indus +16*(SIC >=	6040	 & SIC <= 	6049	);
indus = indus +16*(SIC >=	6050	 & SIC <= 	6059	);
indus = indus +16*(SIC >=	6060	 & SIC <= 	6062	);
indus = indus +16*(SIC >=	6080	 & SIC <= 	6082	);
indus = indus +16*(SIC >=	6090	 & SIC <= 	6099	);
indus = indus +16*(SIC >=	6100	 & SIC <= 	6100	);
indus = indus +16*(SIC >=	6110	 & SIC <= 	6111	);
indus = indus +16*(SIC >=	6112	 & SIC <= 	6112	);
indus = indus +16*(SIC >=	6120	 & SIC <= 	6129	);
indus = indus +16*(SIC >=	6140	 & SIC <= 	6149	);
indus = indus +16*(SIC >=	6150	 & SIC <= 	6159	);
indus = indus +16*(SIC >=	6160	 & SIC <= 	6163	);
indus = indus +16*(SIC >=	6172	 & SIC <= 	6172	);
indus = indus +16*(SIC >=	6199	 & SIC <= 	6199	);
indus = indus +16*(SIC >=	6200	 & SIC <= 	6299	);
indus = indus +16*(SIC >=	6300	 & SIC <= 	6300	);
indus = indus +16*(SIC >=	6310	 & SIC <= 	6312	);
indus = indus +16*(SIC >=	6320	 & SIC <= 	6324	);
indus = indus +16*(SIC >=	6330	 & SIC <= 	6331	);
indus = indus +16*(SIC >=	6350	 & SIC <= 	6351	);
indus = indus +16*(SIC >=	6360	 & SIC <= 	6361	);
indus = indus +16*(SIC >=	6370	 & SIC <= 	6371	);
indus = indus +16*(SIC >=	6390	 & SIC <= 	6399	);
indus = indus +16*(SIC >=	6400	 & SIC <= 	6411	);
indus = indus +16*(SIC >=	6500	 & SIC <= 	6500	);
indus = indus +16*(SIC >=	6510	 & SIC <= 	6510	);
indus = indus +16*(SIC >=	6512	 & SIC <= 	6512	);
indus = indus +16*(SIC >=	6513	 & SIC <= 	6513	);
indus = indus +16*(SIC >=	6514	 & SIC <= 	6514	);
indus = indus +16*(SIC >=	6515	 & SIC <= 	6515	);
indus = indus +16*(SIC >=	6517	 & SIC <= 	6519	);
indus = indus +16*(SIC >=	6530	 & SIC <= 	6531	);
indus = indus +16*(SIC >=	6532	 & SIC <= 	6532	);
indus = indus +16*(SIC >=	6540	 & SIC <= 	6541	);
indus = indus +16*(SIC >=	6550	 & SIC <= 	6553	);
indus = indus +16*(SIC >=	6611	 & SIC <= 	6611	);
indus = indus +16*(SIC >=	6700	 & SIC <= 	6700	);
indus = indus +16*(SIC >=	6710	 & SIC <= 	6719	);
indus = indus +16*(SIC >=	6720	 & SIC <= 	6722	);
indus = indus +16*(SIC >=	6723	 & SIC <= 	6723	);
indus = indus +16*(SIC >=	6724	 & SIC <= 	6724	);
indus = indus +16*(SIC >=	6725	 & SIC <= 	6725	);
indus = indus +16*(SIC >=	6726	 & SIC <= 	6726	);
indus = indus +16*(SIC >=	6730	 & SIC <= 	6733	);
indus = indus +16*(SIC >=	6790	 & SIC <= 	6790	);
indus = indus +16*(SIC >=	6792	 & SIC <= 	6792	);
indus = indus +16*(SIC >=	6794	 & SIC <= 	6794	);
indus = indus +16*(SIC >=	6795	 & SIC <= 	6795	);
indus = indus +16*(SIC >=	6798	 & SIC <= 	6798	);
indus = indus +16*(SIC >=	6799	 & SIC <= 	6799	);


%  17 Other 

indus((SIC)>0 & (indus==0))=17;



FF17 = indus;

FF17Names=[{1},{'Food'},{'Food'}; ...
{2},{'Mines'},{'Mining and Minerals'}; ...
{3},{'Oil'},{'Oil and Petroleum Products'}; ...
{4},{'Clths'},{'Textiles, Apparel & Footware'}; ...
{5},{'Durbl'},{'Consumer Durables'}; ...
{6},{'Chems'},{'Chemicals'}; ...
{7},{'Cnsum'},{'Drugs, Soap, Prfums, Tobacco'}; ...
{8},{'Cnstr'},{'Construction and Construction Materials'}; ...
{9},{'Steel'},{'Steel Works Etc'}; ...
{10},{'FabPr'},{'Fabricated Products'}; ...
{11},{'Machn'},{'Machinery and Business Equipment'}; ...
{12},{'Cars'},{'Automobiles'}; ...
{13},{'Trans'},{'Transportation'}; ...
{14},{'Utils'},{'Utilities'}; ...
{15},{'Rtail'},{'Retail Stores'}; ...
{16},{'Finan'},{'Banks, Insurance Companies, and Other Financials'}; ...
{17},{'Other'},{'Almost Nothing'};];

FF17Names=array2table(FF17Names);
FF17Names.Properties.VariableNames={'number','shortName','longName'};
end


