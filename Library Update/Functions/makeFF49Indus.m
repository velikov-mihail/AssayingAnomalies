function [FF49, FF49Names] = makeFF49Indus(SIC) 
% PURPOSE: This function creates a Fama and French 49-industry
% classification index and a table with the industry names
%------------------------------------------------------------------------------------------
% USAGE:   
% [FF49, FF49Names] = makeFF49Indus(SIC)          
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -SIC - a matrix containing SIC codes
%------------------------------------------------------------------------------------------
% Output:
%        -inds - matrix with the industries indicators
%        -FF49Names - table with the industry names
%------------------------------------------------------------------------------------------
% Examples:
%
% [FF49, FF49Names] = makeFF49Indus(SIC)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% 1 Agric  Agriculture
%           0100-0199 Agric production - crops
%           0200-0299 Agric production - livestock
%           0700-0799 Agricultural services
%           0910-0919 Commercial fishing
%           2048-2048 Prepared feeds for animals
          
indus = (SIC >= 100 & SIC <= 299);
indus = indus + (SIC >= 700 & SIC <= 799);
indus = indus + (SIC >= 910 & SIC <= 919);
indus = indus + (SIC == 2048);

%  2 Food   Food Products
%           2000-2009 Food and kindred products
%           2010-2019 Meat products
%           2020-2029 Dairy products
%           2030-2039 Canned-preserved fruits-vegs
%           2040-2046 Flour and other grain mill products
%           2050-2059 Bakery products
%           2060-2063 Sugar and confectionery products
%           2070-2079 Fats and oils
%           2090-2092 Misc food preps
%           2095-2095 Roasted coffee
%           2098-2099 Misc food preparations

indus = indus + 2*(SIC >= 2000 & SIC <= 2046);
indus = indus + 2*(SIC >= 2050 & SIC <= 2063);
indus = indus + 2*(SIC >= 2070 & SIC <= 2079);
indus = indus + 2*(SIC >= 2090 & SIC <= 2092);
indus = indus + 2*(SIC == 2095);
indus = indus + 2*(SIC >= 2098 & SIC <= 2099);

%  3 Soda   Candy & Soda
%           2064-2068 Candy and other confectionery
%           2086-2086 Bottled-canned soft drinks
%           2087-2087 Flavoring syrup
%           2096-2096 Potato chips
%           2097-2097 Manufactured ice

indus = indus + 3*(SIC >= 2064 & SIC <= 2068);
indus = indus + 3*(SIC >= 2086 & SIC <= 2087);
indus = indus + 3*(SIC >= 2096 & SIC <= 2097);

%  4 Beer   Beer & Liquor
%           2080-2080 Beverages
%           2082-2082 Malt beverages
%           2083-2083 Malt
%           2084-2084 Wine
%           2085-2085 Distilled and blended liquors

indus = indus + 4*(SIC == 2080);
indus = indus + 4*(SIC >= 2082 & SIC <= 2085);

%  5 Smoke  Tobacco Products
%           2100-2199 Tobacco products

indus = indus + 5*(SIC >= 2100 & SIC <= 2199);

%  6 Toys   Recreation
%           0920-0999 Fishing, hunting & trapping
%           3650-3651 Household audio visual equip
%           3652-3652 Phonographic records
%           3732-3732 Boat building and repair
%           3930-3931 Musical instruments
%           3940-3949 Toys

indus = indus + 6*(SIC >= 920 & SIC <= 999);
indus = indus + 6*(SIC >= 3650 & SIC <= 3652);
indus = indus + 6*(SIC == 3732);
indus = indus + 6*(SIC >= 3930 & SIC <= 3931);
indus = indus + 6*(SIC >= 3940 & SIC <= 3949);

%  7 Fun    Entertainment
%           7800-7829 Services - motion picture production and distribution
%           7830-7833 Services - motion picture theatres
%           7840-7841 Services - video rental
%           7900-7900 Services - amusement and recreation
%           7910-7911 Services - dance studios
%           7920-7929 Services - bands, entertainers
%           7930-7933 Services - bowling centers
%           7940-7949 Services - professional sports
%           7980-7980 Amusement and recreation services (?)
%           7990-7999 Services - misc entertainment

indus = indus + 7*(SIC >= 7800 & SIC <= 7833);
indus = indus + 7*(SIC >= 7840 & SIC <= 7841);
indus = indus + 7*(SIC == 7900);
indus = indus + 7*(SIC >= 7910 & SIC <= 7911);
indus = indus + 7*(SIC >= 7920 & SIC <= 7933);
indus = indus + 7*(SIC >= 7940 & SIC <= 7949);
indus = indus + 7*(SIC == 7980);
indus = indus + 7*(SIC >= 7990 & SIC <= 7999);

%  8 Books  Printing and Publishing
%           2700-2709 Printing publishing and allied
%           2710-2719 Newspapers: publishing-printing
%           2720-2729 Periodicals: publishing-printing
%           2730-2739 Books: publishing-printing
%           2740-2749 Misc publishing
%           2770-2771 Greeting card publishing
%           2780-2789 Book binding
%           2790-2799 Service industries for print trade

indus = indus + 8*(SIC >= 2700 & SIC <= 2749);
indus = indus + 8*(SIC >= 2770 & SIC <= 2771);
indus = indus + 8*(SIC >= 2780 & SIC <= 2799);

%  9 Hshld  Consumer Goods
%           2047-2047 Dog and cat food
%           2391-2392 Curtains, home furnishings
%           2510-2519 Household furniture
%           2590-2599 Misc furniture and fixtures
%           2840-2843 Soap & other detergents
%           2844-2844 Perfumes cosmetics
%           3160-3161 Luggage
%           3170-3171 Handbags and purses
%           3172-3172 Personal leather goods, except handbags
%           3190-3199 Leather goods
%           3229-3229 Pressed and blown glass
%           3260-3260 Pottery and related products
%           3262-3263 China and earthenware table articles
%           3269-3269 Pottery products
%           3230-3231 Glass products
%           3630-3639 Household appliances
%           3750-3751 Motorcycles, bicycles and parts  (Harley & Huffy)
%           3800-3800 Misc inst, photo goods, watches
%           3860-3861 Photographic equip  (Kodak etc, but also Xerox)
%           3870-3873 Watches clocks and parts
%           3910-3911 Jewelry-precious metals
%           3914-3914 Silverware
%           3915-3915 Jewelers' findings, materials
%           3960-3962 Costume jewelry and notions
%           3991-3991 Brooms and brushes
%           3995-3995 Burial caskets

indus = indus + 9*(SIC == 2047);
indus = indus + 9*(SIC >= 2391 & SIC <= 2392);
indus = indus + 9*(SIC >= 2510 & SIC <= 2519);
indus = indus + 9*(SIC >= 2590 & SIC <= 2599);
indus = indus + 9*(SIC >= 2840 & SIC <= 2844);
indus = indus + 9*(SIC >= 3160 & SIC <= 3161);
indus = indus + 9*(SIC >= 3170 & SIC <= 3172);
indus = indus + 9*(SIC >= 3190 & SIC <= 3199);
indus = indus + 9*(SIC == 3229);
indus = indus + 9*(SIC == 3260);
indus = indus + 9*(SIC >= 3262 & SIC <= 3263);
indus = indus + 9*(SIC == 3269);
indus = indus + 9*(SIC >= 3230 & SIC <= 3231);
indus = indus + 9*(SIC >= 3630 & SIC <= 3639);
indus = indus + 9*(SIC >= 3750 & SIC <= 3751);
indus = indus + 9*(SIC == 3800);
indus = indus + 9*(SIC >= 3860 & SIC <= 3861);
indus = indus + 9*(SIC >= 3870 & SIC <= 3873);
indus = indus + 9*(SIC >= 3910 & SIC <= 3911);
indus = indus + 9*(SIC >= 3914 & SIC <= 3915);
indus = indus + 9*(SIC >= 3960 & SIC <= 3962);
indus = indus + 9*(SIC == 3991);
indus = indus + 9*(SIC == 3995);

% 10 Clths  Apparel
%           2300-2390 Apparel and other finished products
%           3020-3021 Rubber and plastics footwear
%           3100-3111 Leather tanning and finishing
%           3130-3131 Boot, shoe cut stock, findings
%           3140-3149 Footware except rubber
%           3150-3151 Leather gloves and mittens
%           3963-3965 Fasteners, buttons, needles, pins

indus = indus + 10*(SIC >= 2300 & SIC <= 2390);
indus = indus + 10*(SIC >= 3020 & SIC <= 3021);
indus = indus + 10*(SIC >= 3100 & SIC <= 3111);
indus = indus + 10*(SIC >= 3130 & SIC <= 3131);
indus = indus + 10*(SIC >= 3140 & SIC <= 3151);
indus = indus + 10*(SIC >= 3963 & SIC <= 3965);

% 11 Hlth   Healthcare
%           8000-8099 Services - health

indus = indus + 11*(SIC >= 8000 & SIC <= 8099);

% 12 MedEq  Medical Equipment
%           3693-3693 X-ray, electromedical app
%           3840-3849 Surg & med instru
%           3850-3851 Ophthalmic goods

indus = indus + 12*(SIC == 3693);
indus = indus + 12*(SIC >= 3840 & SIC <= 3851);

% 13 Drugs  Pharmaceutical Products
%           2830-2830 Drugs
%           2831-2831 Biological products
%           2833-2833 Medicinal chemicals
%           2834-2834 Pharmaceutical preparations
%           2835-2835 In vitro, in vivo diagnostics
%           2836-2836 Biological products, except diagnostics

indus = indus + 13*(SIC >= 2830 & SIC <= 2831);
indus = indus + 13*(SIC >= 2833 & SIC <= 2836);

% 14 Chems  Chemicals
%           2800-2809 Chemicals and allied products
%           2810-2819 Industrial inorganical chems
%           2820-2829 Plastic material & synthetic resin
%           2850-2859 Paints
%           2860-2869 Industrial organic chems
%           2870-2879 Agriculture chemicals
%           2890-2899 Misc chemical products

indus = indus + 14*(SIC >= 2800 & SIC <= 2829);
indus = indus + 14*(SIC >= 2850 & SIC <= 2879);
indus = indus + 14*(SIC >= 2890 & SIC <= 2899);

% 15 Rubbr  Rubber and Plastic Products
%           3031-3031 Reclaimed rubber
%           3041-3041 Rubber & plastic hose and belting
%           3050-3053 Gaskets, hoses, etc
%           3060-3069 Fabricated rubber products
%           3070-3079 Misc rubber products (?)
%           3080-3089 Misc plastic products
%           3090-3099 Misc rubber and plastic products (?)

indus = indus + 15*(SIC == 3031);
indus = indus + 15*(SIC == 3041);
indus = indus + 15*(SIC >= 3050 & SIC <= 3053);
indus = indus + 15*(SIC >= 3060 & SIC <= 3099);

% 16 Txtls  Textiles
%           2200-2269 Textile mill products
%           2270-2279 Floor covering mills
%           2280-2284 Yarn and thread mills
%           2290-2295 Misc textile goods
%           2297-2297 Nonwoven fabrics
%           2298-2298 Cordage and twine
%           2299-2299 Misc textile products
%           2393-2395 Textile bags, canvas products
%           2397-2399 Misc textile products

indus = indus + 16*(SIC >= 2200 & SIC <= 2284);
indus = indus + 16*(SIC >= 2290 & SIC <= 2295);
indus = indus + 16*(SIC >= 2297 & SIC <= 2299);
indus = indus + 16*(SIC >= 2393 & SIC <= 2395);
indus = indus + 16*(SIC >= 2397 & SIC <= 2399);

% 17 BldMt  Construction Materials
%           0800-0899 Forestry
%           2400-2439 Lumber and wood products
%           2450-2459 Wood buildings-mobile homes
%           2490-2499 Misc wood products
%           2660-2661 Building paper and board mills
%           2950-2952 Paving & roofing materials
%           3200-3200 Stone, clay, glass, concrete etc
%           3210-3211 Flat glass
%           3240-3241 Cement hydraulic
%           3250-3259 Structural clay prods
%           3261-3261 Vitreous china plumbing fixtures
%           3264-3264 Porcelain electrical supply
%           3270-3275 Concrete gypsum & plaster
%           3280-3281 Cut stone and stone products
%           3290-3293 Abrasive and asbestos products
%           3295-3299 Non-metalic mineral products
%           3420-3429 Handtools and hardware
%           3430-3433 Heating equip & plumbing fix
%           3440-3441 Fabicated struct metal products
%           3442-3442 Metal doors, frames
%           3446-3446 Architectual or ornamental metal work
%           3448-3448 Pre-fab metal buildings
%           3449-3449 Misc structural metal work
%           3450-3451 Screw machine products
%           3452-3452 Bolts, nuts screws
%           3490-3499 Misc fabricated metal products
%           3996-3996 Hard surface floor cover

indus = indus + 17*(SIC >= 800 & SIC <= 899);
indus = indus + 17*(SIC >= 2400 & SIC <= 2439);
indus = indus + 17*(SIC >= 2450 & SIC <= 2459);
indus = indus + 17*(SIC >= 2490 & SIC <= 2499);
indus = indus + 17*(SIC >= 2660 & SIC <= 2661);
indus = indus + 17*(SIC >= 2950 & SIC <= 2952);
indus = indus + 17*(SIC == 3200);
indus = indus + 17*(SIC >= 3210 & SIC <= 3211);
indus = indus + 17*(SIC >= 3240 & SIC <= 3241);
indus = indus + 17*(SIC >= 3250 & SIC <= 3259);
indus = indus + 17*(SIC == 3261);
indus = indus + 17*(SIC == 3264);
indus = indus + 17*(SIC >= 3270 & SIC <= 3275);
indus = indus + 17*(SIC >= 3280 & SIC <= 3281);
indus = indus + 17*(SIC >= 3290 & SIC <= 3293);
indus = indus + 17*(SIC >= 3295 & SIC <= 3299);
indus = indus + 17*(SIC >= 3420 & SIC <= 3433);
indus = indus + 17*(SIC >= 3440 & SIC <= 3442);
indus = indus + 17*(SIC == 3446);
indus = indus + 17*(SIC >= 3448 & SIC <= 3452);
indus = indus + 17*(SIC >= 3490 & SIC <= 3499);
indus = indus + 17*(SIC == 3996);

% 18 Cnstr  Construction
%           1500-1511 Build construction - general contractors
%           1520-1529 Gen building contractors - residential
%           1530-1539 Operative builders
%           1540-1549 Gen building contractors - non-residential
%           1600-1699 Heavy Construction - not building contractors
%           1700-1799 Construction - special contractors

indus = indus + 18*(SIC >= 1500 & SIC <= 1511);
indus = indus + 18*(SIC >= 1520 & SIC <= 1549);
indus = indus + 18*(SIC >= 1600 & SIC <= 1799);

% 19 Steel  Steel Works Etc
%           3300-3300 Primary metal industries
%           3310-3317 Blast furnaces & steel works
%           3320-3325 Iron & steel foundries
%           3330-3339 Prim smelt-refin nonfer metals
%           3340-3341 Secondary smelt-refin nonfer metals
%           3350-3357 Rolling & drawing nonferous metals
%           3360-3369 Non-ferrous foundries and casting
%           3370-3379 Steel works etc
%           3390-3399 Misc primary metal products

indus = indus + 19*(SIC == 3300);
indus = indus + 19*(SIC >= 3310 & SIC <= 3317);
indus = indus + 19*(SIC >= 3320 & SIC <= 3325);
indus = indus + 19*(SIC >= 3330 & SIC <= 3341);
indus = indus + 19*(SIC >= 3350 & SIC <= 3357);
indus = indus + 19*(SIC >= 3360 & SIC <= 3379);
indus = indus + 19*(SIC >= 3390 & SIC <= 3399);

% 20 FabPr  Fabricated Products
%           3400-3400 Fabricated metal, except machinery and trans eq
%           3443-3443 Fabricated plate work
%           3444-3444 Sheet metal work
%           3460-3469 Metal forgings and stampings
%           3470-3479 Coating and engraving

indus = indus + 20*(SIC == 3400);
indus = indus + 20*(SIC >= 3443 & SIC <= 3444);
indus = indus + 20*(SIC >= 3460 & SIC <= 3479);

% 21 Mach   Machinery
%           3510-3519 Engines & turbines
%           3520-3529 Farm and garden machinery
%           3530-3530 Constr, mining material handling machinery
%           3531-3531 Construction machinery
%           3532-3532 Mining machinery, except oil field
%           3533-3533 Oil field machinery
%           3534-3534 Elevators
%           3535-3535 Conveyors
%           3536-3536 Cranes, hoists
%           3538-3538 Machinery
%           3540-3549 Metalworking machinery 
%           3550-3559 Special industry machinery
%           3560-3569 General industrial machinery
%           3580-3580 Refrig & service ind machines
%           3581-3581 Automatic vending machines
%           3582-3582 Commercial laundry and drycleaning machines
%           3585-3585 Air conditioning, heating, refrid eq
%           3586-3586 Measuring and dispensing pumps
%           3589-3589 Service industry machinery
%           3590-3599 Misc industrial and commercial equipment and mach

indus = indus + 21*(SIC >= 3510 & SIC <= 3536);
indus = indus + 21*(SIC == 3538);
indus = indus + 21*(SIC >= 3540 & SIC <= 3569);
indus = indus + 21*(SIC >= 3580 & SIC <= 3582);
indus = indus + 21*(SIC >= 3585 & SIC <= 3586);
indus = indus + 21*(SIC >= 3589 & SIC <= 3599);

% 22 ElcEq  Electrical Equipment
%           3600-3600 Elec mach eq & supply
%           3610-3613 Elec transmission
%           3620-3621 Electrical industrial appar
%           3623-3629 Electrical industrial appar
%           3640-3644 Electric lighting, wiring
%           3645-3645 Residential lighting fixtures
%           3646-3646 Commercial lighting 
%           3648-3649 Lighting equipment
%           3660-3660 Communication equip
%           3690-3690 Miscellaneous electrical machinery and equip
%           3691-3692 Storage batteries
%           3699-3699 Electrical machinery and equip

indus = indus + 22*(SIC == 3600);
indus = indus + 22*(SIC >= 3610 & SIC <= 3613);
indus = indus + 22*(SIC >= 3620 & SIC <= 3621);
indus = indus + 22*(SIC >= 3623 & SIC <= 3629);
indus = indus + 22*(SIC >= 3640 & SIC <= 3646);
indus = indus + 22*(SIC >= 3648 & SIC <= 3649);
indus = indus + 22*(SIC == 3660);
indus = indus + 22*(SIC >= 3690 & SIC <= 3692);
indus = indus + 22*(SIC == 3699);

% 23 Autos  Automobiles and Trucks
%           2296-2296 Tire cord and fabric
%           2396-2396 Auto trim
%           3010-3011 Tires and inner tubes
%           3537-3537 Trucks, tractors, trailers
%           3647-3647 Vehicular lighting
%           3694-3694 Elec eq, internal combustion engines
%           3700-3700 Transportation equipment
%           3710-3710 Motor vehicles and motor vehicle equip
%           3711-3711 Motor vehicles & car bodies
%           3713-3713 Truck & bus bodies
%           3714-3714 Motor vehicle parts
%           3715-3715 Truck trailers
%           3716-3716 Motor homes
%           3790-3791 Misc trans equip
%           3792-3792 Travel trailers and campers
%           3799-3799 Misc trans equip

indus = indus + 23*(SIC == 2296);
indus = indus + 23*(SIC == 2396);
indus = indus + 23*(SIC >= 3010 & SIC <= 3011);
indus = indus + 23*(SIC == 3537);
indus = indus + 23*(SIC == 3647);
indus = indus + 23*(SIC == 3694);
indus = indus + 23*(SIC == 3700);
indus = indus + 23*(SIC >= 3710 & SIC <= 3711);
indus = indus + 23*(SIC >= 3713 & SIC <= 3716);
indus = indus + 23*(SIC >= 3790 & SIC <= 3792);
indus = indus + 23*(SIC == 3799);

% 24 Aero   Aircraft
%           3720-3720 Aircraft & parts
%           3721-3721 Aircraft
%           3723-3724 Aircraft engines, engine parts
%           3725-3725 Aircraft parts
%           3728-3729 Aircraft parts

indus = indus + 24*(SIC >= 3720 & SIC <= 3721);
indus = indus + 24*(SIC >= 3723 & SIC <= 3725);
indus = indus + 24*(SIC >= 3728 & SIC <= 3729);

% 25 Ships  Shipbuilding, Railroad Equipment
%           3730-3731 Ship building and repair
%           3740-3743 Railroad Equipment

indus = indus + 25*(SIC >= 3730 & SIC <= 3731);
indus = indus + 25*(SIC >= 3740 & SIC <= 3743);

% 26 Guns   Defense
%           3760-3769 Guided missiles and space vehicles
%           3795-3795 Tanks and tank components
%           3480-3489 Ordnance & accessories

indus = indus + 26*(SIC >= 3760 & SIC <= 3769);
indus = indus + 26*(SIC == 3795);
indus = indus + 26*(SIC >= 3480 & SIC <= 3489);

% 27 Gold   Precious Metals
%           1040-1049 Gold & silver ores

indus = indus + 27*(SIC >= 1040 & SIC <= 1049);

% 28 Mines  Non-Metallic and Industrial Metal Mining
%           1000-1009 Metal mining
%           1010-1019 Iron ores
%           1020-1029 Copper ores
%           1030-1039 Lead and zinc ores
%           1050-1059 Bauxite and other aluminum ores                 
%           1060-1069 Ferroalloy ores
%           1070-1079 Mining
%           1080-1089 Mining services
%           1090-1099 Misc metal ores
%           1100-1119 Anthracite mining                               
%           1400-1499 Mining and quarrying non-metalic minerals

indus = indus + 28*(SIC >= 1000 & SIC <= 1039);
indus = indus + 28*(SIC >= 1050 & SIC <= 1119);
indus = indus + 28*(SIC >= 1400 & SIC <= 1499);

% 29 Coal   Coal
%           1200-1299 Bituminous coal

indus = indus + 29*(SIC >= 1200 & SIC <= 1299);

% 30 Oil    Petroleum and Natural Gas
%           1300-1300 Oil and gas extraction
%           1310-1319 Crude petroleum & natural gas
%           1320-1329 Natural gas liquids
%           1330-1339 Petroleum and natural gas
%           1370-1379 Petroleum and natural gas
%           1380-1380 Oil and gas field services
%           1381-1381 Drilling oil & gas wells
%           1382-1382 Oil-gas field exploration
%           1389-1389 Oil and gas field services
%           2900-2912 Petroleum refining
%           2990-2999 Misc petroleum products

indus = indus + 30*(SIC == 1300);
indus = indus + 30*(SIC >= 1310 & SIC <= 1339);
indus = indus + 30*(SIC >= 1370 & SIC <= 1382);
indus = indus + 30*(SIC == 1389);
indus = indus + 30*(SIC >= 2900 & SIC <= 2912);
indus = indus + 30*(SIC >= 2990 & SIC <= 2999);

% 31 Util   Utilities
%           4900-4900 Electric, gas, sanitary services
%           4910-4911 Electric services
%           4920-4922 Natural gas transmission
%           4923-4923 Natural gas transmission-distr
%           4924-4925 Natural gas distribution
%           4930-4931 Electric and other services combined
%           4932-4932 Gas and other services combined
%           4939-4939 Combination utilities
%           4940-4942 Water supply

indus = indus + 31*(SIC == 4900);
indus = indus + 31*(SIC >= 4910 & SIC <= 4911);
indus = indus + 31*(SIC >= 4920 & SIC <= 4925);
indus = indus + 31*(SIC >= 4930 & SIC <= 4932);
indus = indus + 31*(SIC >= 4939 & SIC <= 4942);

% 32 Telcm  Communication
%           4800-4800 Communications
%           4810-4813 Telephone communications
%           4820-4822 Telegraph and other message communication
%           4830-4839 Radio-TV Broadcasters
%           4840-4841 Cable and other pay TV services
%           4880-4889 Communications
%           4890-4890 Communication services (Comsat)
%           4891-4891 Cable TV operators
%           4892-4892 Telephone interconnect
%           4899-4899 Communication services

indus = indus + 32*(SIC == 4800);
indus = indus + 32*(SIC >= 4810 & SIC <= 4813);
indus = indus + 32*(SIC >= 4820 & SIC <= 4822);
indus = indus + 32*(SIC >= 4830 & SIC <= 4841);
indus = indus + 32*(SIC >= 4880 & SIC <= 4892);
indus = indus + 32*(SIC == 4899);

% 33 PerSv  Personal Services
%           7020-7021 Rooming and boarding houses
%           7030-7033 Camps and recreational vehicle parks
%           7200-7200 Services - personal
%           7210-7212 Services - laundry, cleaners
%           7214-7214 Services - diaper service                                  
%           7215-7216 Services - coin-op cleaners, dry cleaners
%           7217-7217 Services - carpet, upholstery cleaning
%           7219-7219 Services - laundry, cleaners
%           7220-7221 Services - photo studios, portrait
%           7230-7231 Services - beauty shops
%           7240-7241 Services - barber shops
%           7250-7251 Services - shoe repair
%           7260-7269 Services - funeral
%           7270-7290 Services - misc
%           7291-7291 Services - tax return
%           7292-7299 Services - misc
%           7395-7395 Services - photofinishing labs (School pictures)
%           7500-7500 Services - auto repair, services
%           7520-7529 Services - automobile parking
%           7530-7539 Services - auto repair shops
%           7540-7549 Services - auto services, except repair (car washes)
%           7600-7600 Services - Misc repair services
%           7620-7620 Services - Electrical repair shops
%           7622-7622 Services - Radio and TV repair shops
%           7623-7623 Services - Refridg and air conditioner repair
%           7629-7629 Services - Electrical repair shops
%           7630-7631 Services - Watch, clock and jewelry repair
%           7640-7641 Services - Reupholster, furniture repair
%           7690-7699 Services - Misc repair shops
%           8100-8199 Services - legal
%           8200-8299 Services - educational
%           8300-8399 Services - social services
%           8400-8499 Services - museums, galleries, botanic gardens
%           8600-8699 Services - membership organizations
%           8800-8899 Services - private households
%           7510-7515 Services - truck, auto rental and leasing

indus = indus + 33*(SIC >= 7020 & SIC <= 7021);
indus = indus + 33*(SIC >= 7030 & SIC <= 7033);
indus = indus + 33*(SIC == 7200);
indus = indus + 33*(SIC >= 7210 & SIC <= 7212);
indus = indus + 33*(SIC >= 7214 & SIC <= 7217);
indus = indus + 33*(SIC >= 7219 & SIC <= 7221);
indus = indus + 33*(SIC >= 7230 & SIC <= 7231);
indus = indus + 33*(SIC >= 7240 & SIC <= 7241);
indus = indus + 33*(SIC >= 7250 & SIC <= 7251);
indus = indus + 33*(SIC >= 7260 & SIC <= 7299);
indus = indus + 33*(SIC == 7395);
indus = indus + 33*(SIC == 7500);
indus = indus + 33*(SIC >= 7520 & SIC <= 7549);
indus = indus + 33*(SIC == 7600);
indus = indus + 33*(SIC == 7620);
indus = indus + 33*(SIC >= 7622 & SIC <= 7623);
indus = indus + 33*(SIC >= 7629 & SIC <= 7631);
indus = indus + 33*(SIC >= 7640 & SIC <= 7641);
indus = indus + 33*(SIC >= 7690 & SIC <= 7699);
indus = indus + 33*(SIC >= 8100 & SIC <= 8499);
indus = indus + 33*(SIC >= 8600 & SIC <= 8699);
indus = indus + 33*(SIC >= 8800 & SIC <= 8899);
indus = indus + 33*(SIC >= 7510 & SIC <= 7515);

% 34 BusSv  Business Services
%           2750-2759 Commercial printing
%           3993-3993 Signs, advertising specialty
%           7218-7218 Services - industrial launderers
%           7300-7300 Services - business services
%           7310-7319 Services - advertising
%           7320-7329 Services - credit reporting agencies, collection services
%           7330-7339 Services - mailing, reproduction, commercial art
%           7340-7342 Services - services to dwellings, other buildings
%           7349-7349 Services - cleaning and builging maint
%           7350-7351 Services - misc equip rental and leasing
%           7352-7352 Services - medical equip rental
%           7353-7353 Services - heavy construction equip rental
%           7359-7359 Services - equip rental and leasing
%           7360-7369 Services - personnel supply services
%           7374-7374 Services - computer processing, data prep
%           7376-7376 Services - computer facilities management service
%           7377-7377 Services - computer rental and leasing
%           7378-7378 Services - computer maintanence and repair
%           7379-7379 Services - computer related services
%           7380-7380 Services - misc business services
%           7381-7382 Services - security
%           7383-7383 Services - news syndicates
%           7384-7384 Services - photofinishing labs
%           7385-7385 Services - telephone interconnections
%           7389-7390 Services - misc business services
%           7391-7391 Services - R&D labs
%           7392-7392 Services - management consulting & P.R.
%           7393-7393 Services - detective and protective (ADT)
%           7394-7394 Services - equipment rental & leasing
%           7396-7396 Services - trading stamp services                          
%           7397-7397 Services - commercial testing labs
%           7399-7399 Services - business services
%           7519-7519 Services - trailer rental and leasing
%           8700-8700 Services - engineering, accounting, research, management
%           8710-8713 Services - engineering, accounting, surveying
%           8720-8721 Services - accounting, auditing, bookkeeping
%           8730-8734 Services - research, development, testing labs
%           8740-8748 Services - management, public relations, consulting
%           8900-8910 Services - misc
%           8911-8911 Services - engineering & architect
%           8920-8999 Services - misc
%           4220-4229 Warehousing and storage

indus = indus + 34*(SIC >= 2750 & SIC <= 2759);
indus = indus + 34*(SIC == 3993);
indus = indus + 34*(SIC == 7218);
indus = indus + 34*(SIC == 7300);
indus = indus + 34*(SIC >= 7310 & SIC <= 7342);
indus = indus + 34*(SIC >= 7349 & SIC <= 7353);
indus = indus + 34*(SIC >= 7359 & SIC <= 7369);
indus = indus + 34*(SIC == 7374);
indus = indus + 34*(SIC >= 7376 & SIC <= 7385);
indus = indus + 34*(SIC >= 7389 & SIC <= 7394);
indus = indus + 34*(SIC >= 7396 & SIC <= 7397);
indus = indus + 34*(SIC == 7399);
indus = indus + 34*(SIC == 7519);
indus = indus + 34*(SIC == 8700);
indus = indus + 34*(SIC >= 8710 & SIC <= 8713);
indus = indus + 34*(SIC >= 8720 & SIC <= 8721);
indus = indus + 34*(SIC >= 8730 & SIC <= 8734);
indus = indus + 34*(SIC >= 8740 & SIC <= 8748);
indus = indus + 34*(SIC >= 8900 & SIC <= 8910);
indus = indus + 34*(SIC == 8911);
indus = indus + 34*(SIC >= 8920 & SIC <= 8999);
indus = indus + 34*(SIC >= 4220 & SIC <= 4229);

% 35 Hardw  Computers
%           3570-3579 Office computers
%           3680-3680 Computers
%           3681-3681 Computers - mini
%           3682-3682 Computers - mainframe
%           3683-3683 Computers - terminals
%           3684-3684 Computers - disk & tape drives
%           3685-3685 Computers - optical scanners
%           3686-3686 Computers - graphics
%           3687-3687 Computers - office automation systems
%           3688-3688 Computers - peripherals
%           3689-3689 Computers - equipment
%           3695-3695 Magnetic and optical recording media

indus = indus + 35*(SIC >= 3570 & SIC <= 3579);
indus = indus + 35*(SIC >= 3680 & SIC <= 3689);
indus = indus + 35*(SIC == 3695);

% 36 Softw  Computer Software 
%           7370-7372 Services - computer programming and data processing	  
%           7373-7373 Computer integrated systems design
%           7375-7375 Services - information retrieval services

indus = indus + 36*(SIC >= 7370 & SIC <= 7373);
indus = indus + 36*(SIC == 7375);

% 37 Chips  Electronic Equipment
%           3622-3622 Industrial controls
%           3661-3661 Telephone and telegraph apparatus
%           3662-3662 Communications equipment
%           3663-3663 Radio TV comm equip & apparatus
%           3664-3664 Search, navigation, guidance systems
%           3665-3665 Training equipment & simulators
%           3666-3666 Alarm & signaling products
%           3669-3669 Communication equipment
%           3670-3679 Electronic components
%           3810-3810 Search, detection, navigation, guidance
%           3812-3812 Search, detection, navigation, guidance

indus = indus + 37*(SIC == 3622);
indus = indus + 37*(SIC >= 3661 & SIC <= 3666);
indus = indus + 37*(SIC >= 3669 & SIC <= 3679);
indus = indus + 37*(SIC == 3810);
indus = indus + 37*(SIC == 3812);

% 38 LabEq  Measuring and Control Equipment
%           3811-3811 Engr lab and research equipment
%           3820-3820 Measuring and controlling equipment
%           3821-3821 Lab apparatus and furniture
%           3822-3822 Automatic controls - Envir and applic
%           3823-3823 Industrial measurement instru
%           3824-3824 Totalizing fluid meters
%           3825-3825 Elec meas & test instr
%           3826-3826 Lab analytical instruments
%           3827-3827 Optical instr and lenses
%           3829-3829 Meas and control devices
%           3830-3839 Optical instr and lenses

indus = indus + 38*(SIC == 3811);
indus = indus + 38*(SIC >= 3820 & SIC <= 3827);
indus = indus + 38*(SIC >= 3829 & SIC <= 3839);

% 39 Paper  Business Supplies
%           2520-2549 Office furniture and fixtures
%           2600-2639 Paper and allied products
%           2670-2699 Paper and allied products
%           2760-2761 Manifold business forms
%           3950-3955 Pens pencils and office supplies

indus = indus + 39*(SIC >= 2520 & SIC <= 2549);
indus = indus + 39*(SIC >= 2600 & SIC <= 2639);
indus = indus + 39*(SIC >= 2670 & SIC <= 2699);
indus = indus + 39*(SIC >= 2760 & SIC <= 2761);
indus = indus + 39*(SIC >= 3950 & SIC <= 3955);

% 40 Boxes  Shipping Containers
%           2440-2449 Wood containers
%           2640-2659 Paperboard containers, boxes, drums, tubs
%           3220-3221 Glass containers
%           3410-3412 Metal cans and shipping containers

indus = indus + 40*(SIC >= 2440 & SIC <= 2449);
indus = indus + 40*(SIC >= 2640 & SIC <= 2659);
indus = indus + 40*(SIC >= 3220 & SIC <= 3221);
indus = indus + 40*(SIC >= 3410 & SIC <= 3412);

% 41 Trans  Transportation
%           4000-4013 Railroads-line haul
%           4040-4049 Railway express service                         
%           4100-4100 Transit and passenger trans
%           4110-4119 Local passenger trans
%           4120-4121 Taxicabs
%           4130-4131 Intercity bus trans (Greyhound)
%           4140-4142 Bus charter
%           4150-4151 School buses
%           4170-4173 Motor vehicle terminals, service facilities
%           4190-4199 Misc transit and passenger transportation
%           4200-4200 Motor freight trans, warehousing
%           4210-4219 Trucking
%           4230-4231 Terminal facilities - motor freight
%           4240-4249 Transportation
%           4400-4499 Water transport
%           4500-4599 Air transportation
%           4600-4699 Pipelines, except natural gas
%           4700-4700 Transportation services
%           4710-4712 Freight forwarding
%           4720-4729 Travel agencies, etc
%           4730-4739 Arrange trans - freight and cargo
%           4740-4749 Rental of railroad cars
%           4780-4780 Misc services incidental to trans
%           4782-4782 Inspection and weighing services                
%           4783-4783 Packing and crating
%           4784-4784 Fixed facilities for vehicles, not elsewhere classified
%           4785-4785 Motor vehicle inspection
%           4789-4789 Transportation services

indus = indus + 41*(SIC >= 4000 & SIC <= 4013);
indus = indus + 41*(SIC >= 4040 & SIC <= 4049);
indus = indus + 41*(SIC == 4100);
indus = indus + 41*(SIC >= 4110 & SIC <= 4121);
indus = indus + 41*(SIC >= 4130 & SIC <= 4131);
indus = indus + 41*(SIC >= 4140 & SIC <= 4142);
indus = indus + 41*(SIC >= 4150 & SIC <= 4151);
indus = indus + 41*(SIC >= 4170 & SIC <= 4173);
indus = indus + 41*(SIC >= 4190 & SIC <= 4200);
indus = indus + 41*(SIC >= 4210 & SIC <= 4219);
indus = indus + 41*(SIC >= 4230 & SIC <= 4231);
indus = indus + 41*(SIC >= 4240 & SIC <= 4249);
indus = indus + 41*(SIC >= 4400 & SIC <= 4700);
indus = indus + 41*(SIC >= 4710 & SIC <= 4712);
indus = indus + 41*(SIC >= 4720 & SIC <= 4749);
indus = indus + 41*(SIC == 4780);
indus = indus + 41*(SIC >= 4782 & SIC <= 4785);
indus = indus + 41*(SIC == 4789);

% 42 Whlsl  Wholesale
%           5000-5000 Wholesale - durable goods
%           5010-5015 Wholesale - autos and parts
%           5020-5023 Wholesale - furniture and home furnishings
%           5030-5039 Wholesale - lumber and construction materials
%           5040-5042 Wholesale - professional and commercial equipment and supplies
%           5043-5043 Wholesale - photographic equipment
%           5044-5044 Wholesale - office equipment
%           5045-5045 Wholesale - computers
%           5046-5046 Wholesale - commerical equip
%           5047-5047 Wholesale - medical, dental equip
%           5048-5048 Wholesale - ophthalmic goods
%           5049-5049 Wholesale - professional equip and supplies
%           5050-5059 Wholesale - metals and minerals
%           5060-5060 Wholesale - electrical goods
%           5063-5063 Wholesale - electrical apparatus and equipment
%           5064-5064 Wholesale - electrical appliance TV and radio
%           5065-5065 Wholesale - electronic parts
%           5070-5078 Wholesale - hardware, plumbing, heating equip
%           5080-5080 Wholesale - machinery and equipment
%           5081-5081 Wholesale - machinery and equipment (?)
%           5082-5082 Wholesale - construction and mining equipment
%           5083-5083 Wholesale - farm and garden machinery
%           5084-5084 Wholesale - industrial machinery and equipment
%           5085-5085 Wholesale - industrial supplies
%           5086-5087 Wholesale - machinery and equipment (?)
%           5088-5088 Wholesale - trans eq except motor vehicles
%           5090-5090 Wholesale - misc durable goods
%           5091-5092 Wholesale - sporting goods, toys
%           5093-5093 Wholesale - scrap and waste materials
%           5094-5094 Wholesale - jewelry and watches
%           5099-5099 Wholesale - durable goods
%           5100-5100 Wholesale - nondurable goods
%           5110-5113 Wholesale - paper and paper products
%           5120-5122 Wholesale - drugs & propietary
%           5130-5139 Wholesale - apparel
%           5140-5149 Wholesale - groceries & related prods
%           5150-5159 Wholesale - farm products
%           5160-5169 Wholesale - chemicals & allied prods
%           5170-5172 Wholesale - petroleum and petro prods
%           5180-5182 Wholesale - beer, wine
%           5190-5199 Wholesale - non-durable goods

indus = indus + 42*(SIC == 5000);
indus = indus + 42*(SIC >= 5010 & SIC <= 5015);
indus = indus + 42*(SIC >= 5020 & SIC <= 5023);
indus = indus + 42*(SIC >= 5030 & SIC <= 5060);
indus = indus + 42*(SIC >= 5063 & SIC <= 5065);
indus = indus + 42*(SIC >= 5070 & SIC <= 5078);
indus = indus + 42*(SIC >= 5080 & SIC <= 5088);
indus = indus + 42*(SIC >= 5090 & SIC <= 5094);
indus = indus + 42*(SIC >= 5099 & SIC <= 5113);
indus = indus + 42*(SIC >= 5120 & SIC <= 5122);
indus = indus + 42*(SIC >= 5130 & SIC <= 5172);
indus = indus + 42*(SIC >= 5180 & SIC <= 5182);
indus = indus + 42*(SIC >= 5190 & SIC <= 5199);

% 43 Rtail  Retail 
%           5200-5200 Retail - bldg material, hardware, garden
%           5210-5219 Retail - lumber & other building mat
%           5220-5229 Retail
%           5230-5231 Retail - paint, glass, wallpaper
%           5250-5251 Retail - hardward stores
%           5260-5261 Retail - nurseries, lawn, garden stores
%           5270-5271 Retail - mobile home dealers
%           5300-5300 Retail - general merchandise stores
%           5310-5311 Retail - department stores
%           5320-5320 Retail - general merchandise stores (?)
%           5330-5331 Retail - variety stores
%           5334-5334 Retail - catalog showroom
%           5340-5349 Retail
%           5390-5399 Retail - Misc general merchandise stores
%           5400-5400 Retail - food stores
%           5410-5411 Retail - grocery stores
%           5412-5412 Retail - convenience stores
%           5420-5429 Retail - meat, fish mkt
%           5430-5439 Retail - fruite and vegatable markets
%           5440-5449 Retail - candy, nut, confectionary stores
%           5450-5459 Retail - dairy product stores
%           5460-5469 Retail - bakeries
%           5490-5499 Retail - miscellaneous food stores
%           5500-5500 Retail - auto dealers and gas stations
%           5510-5529 Retail - auto dealers
%           5530-5539 Retail - auto and home supply stores
%           5540-5549 Retail - gasoline service stations
%           5550-5559 Retail - boat dealers
%           5560-5569 Retail - recreational vehicle dealers
%           5570-5579 Retail - motorcycle dealers
%           5590-5599 Retail - automotive dealers
%           5600-5699 Retail - apparel & acces
%           5700-5700 Retail - home furniture and equipment stores
%           5710-5719 Retail - home furnishings stores
%           5720-5722 Retail - household appliance stores
%           5730-5733 Retail - radio, TV and consumer electronic stores
%           5734-5734 Retail - computer and computer software stores
%           5735-5735 Retail - record and tape stores
%           5736-5736 Retail - musical instrument stores
%           5750-5799 Retail
%           5900-5900 Retail - misc
%           5910-5912 Retail - drug & proprietary stores
%           5920-5929 Retail - liquor stores
%           5930-5932 Retail - used merchandise stores
%           5940-5940 Retail - misc
%           5941-5941 Retail - sporting goods stores, bike shops
%           5942-5942 Retail - book stores
%           5943-5943 Retail - stationery stores
%           5944-5944 Retail - jewelry stores
%           5945-5945 Retail - hobby, toy and game shops
%           5946-5946 Retail - camera and photo shop
%           5947-5947 Retail - gift, novelty
%           5948-5948 Retail - luggage
%           5949-5949 Retail - sewing & needlework stores
%           5950-5959 Retail
%           5960-5969 Retail - non-store retailers (catalogs, etc)
%           5970-5979 Retail
%           5980-5989 Retail - fuel & ice stores (Penn Central Co)
%           5990-5990 Retail - retail stores
%           5992-5992 Retail - florists
%           5993-5993 Retail - tobacco stores
%           5994-5994 Retail - newsdealers
%           5995-5995 Retail - computer stores
%           5999-5999 Retail stores

indus = indus + 43*(SIC == 5200);
indus = indus + 43*(SIC >= 5210 & SIC <= 5231);
indus = indus + 43*(SIC >= 5250 & SIC <= 5251);
indus = indus + 43*(SIC >= 5260 & SIC <= 5261);
indus = indus + 43*(SIC >= 5270 & SIC <= 5271);
indus = indus + 43*(SIC == 5300);
indus = indus + 43*(SIC >= 5310 & SIC <= 5311);
indus = indus + 43*(SIC == 5320);
indus = indus + 43*(SIC >= 5330 & SIC <= 5331);
indus = indus + 43*(SIC == 5334);
indus = indus + 43*(SIC >= 5340 & SIC <= 5349);
indus = indus + 43*(SIC >= 5390 & SIC <= 5400);
indus = indus + 43*(SIC >= 5410 & SIC <= 5412);
indus = indus + 43*(SIC >= 5420 & SIC <= 5469);
indus = indus + 43*(SIC >= 5490 & SIC <= 5500);
indus = indus + 43*(SIC >= 5510 & SIC <= 5579);
indus = indus + 43*(SIC >= 5590 & SIC <= 5700);
indus = indus + 43*(SIC >= 5710 & SIC <= 5722);
indus = indus + 43*(SIC >= 5730 & SIC <= 5736);
indus = indus + 43*(SIC >= 5750 & SIC <= 5799);
indus = indus + 43*(SIC == 5900);
indus = indus + 43*(SIC >= 5910 & SIC <= 5912);
indus = indus + 43*(SIC >= 5920 & SIC <= 5932);
indus = indus + 43*(SIC >= 5940 & SIC <= 5990);
indus = indus + 43*(SIC >= 5992 & SIC <= 5995);
indus = indus + 43*(SIC == 5999);

% 44 Meals  Restaraunts, Hotels, Motels
%           5800-5819 Retail - eating places
%           5820-5829 Restaraunts, hotels, motels
%           5890-5899 Eating and drinking places
%           7000-7000 Hotels, other lodging places
%           7010-7019 Hotels motels
%           7040-7049 Membership hotels and lodging
%           7213-7213 Services - linen

indus = indus + 44*(SIC >= 5800 & SIC <= 5829);
indus = indus + 44*(SIC >= 5890 & SIC <= 5899);
indus = indus + 44*(SIC == 7000);
indus = indus + 44*(SIC >= 7010 & SIC <= 7019);
indus = indus + 44*(SIC >= 7040 & SIC <= 7049);
indus = indus + 44*(SIC == 7213);

% 45 Banks  Banking
%           6000-6000 Depository institutions
%           6010-6019 Federal reserve banks
%           6020-6020 Commercial banks
%           6021-6021 National commercial banks
%           6022-6022 State banks - Fed Res System
%           6023-6024 State banks - not Fed Res System
%           6025-6025 National banks - Fed Res System
%           6026-6026 National banks - not Fed Res System
%           6027-6027 National banks, not FDIC                        
%           6028-6029 Banks
%           6030-6036 Savings institutions
%           6040-6059 Banks (?)
%           6060-6062 Credit unions
%           6080-6082 Foreign banks
%           6090-6099 Functions related to deposit banking
%           6100-6100 Nondepository credit institutions
%           6110-6111 Federal credit agencies
%           6112-6113 FNMA
%           6120-6129 S&Ls
%           6130-6139 Agricultural credit institutions                
%           6140-6149 Personal credit institutions (Beneficial)
%           6150-6159 Business credit institutions
%           6160-6169 Mortgage bankers
%           6170-6179 Finance lessors
%           6190-6199 Financial services

indus = indus + 45*(SIC == 6000);
indus = indus + 45*(SIC >= 6010 & SIC <= 6036);
indus = indus + 45*(SIC >= 6040 & SIC <= 6062);
indus = indus + 45*(SIC >= 6080 & SIC <= 6082);
indus = indus + 45*(SIC >= 6090 & SIC <= 6100);
indus = indus + 45*(SIC >= 6110 & SIC <= 6113);
indus = indus + 45*(SIC >= 6120 & SIC <= 6179);
indus = indus + 45*(SIC >= 6190 & SIC <= 6199);

% 46 Insur  Insurance
%           6300-6300 Insurance
%           6310-6319 Life insurance
%           6320-6329 Accident and health insurance
%           6330-6331 Fire, marine, property-casualty ins
%           6350-6351 Surety insurance
%           6360-6361 Title insurance
%           6370-6379 Pension, health, welfare funds
%           6390-6399 Insurance carriers
%           6400-6411 Insurance agents

indus = indus + 46*(SIC == 6300);
indus = indus + 46*(SIC >= 6310 & SIC <= 6331);
indus = indus + 46*(SIC >= 6350 & SIC <= 6351);
indus = indus + 46*(SIC >= 6360 & SIC <= 6361);
indus = indus + 46*(SIC >= 6370 & SIC <= 6379);
indus = indus + 46*(SIC >= 6390 & SIC <= 6411);

% 47 RlEst  Real Estate
%           6500-6500 Real estate
%           6510-6510 Real estate operators
%           6512-6512 Operators - non-resident buildings
%           6513-6513 Operators - apartment buildings
%           6514-6514 Operators - other than apartment
%           6515-6515 Operators - residential mobile home
%           6517-6519 Lessors of real property
%           6520-6529 Real estate
%           6530-6531 Real estate agents and managers
%           6532-6532 Real estate dealers
%           6540-6541 Title abstract offices
%           6550-6553 Real estate developers
%           6590-6599 Real estate
%           6610-6611 Combined real estate, insurance, etc

indus = indus + 47*(SIC == 6500);
indus = indus + 47*(SIC == 6510);
indus = indus + 47*(SIC >= 6512 & SIC <= 6515);
indus = indus + 47*(SIC >= 6517 & SIC <= 6532);
indus = indus + 47*(SIC >= 6540 & SIC <= 6541);
indus = indus + 47*(SIC >= 6550 & SIC <= 6553);
indus = indus + 47*(SIC >= 6590 & SIC <= 6599);
indus = indus + 47*(SIC >= 6610 & SIC <= 6611);

% 48 Fin    Trading
%           6200-6299 Security and commodity brokers
%           6700-6700 Holding, other investment offices
%           6710-6719 Holding offices
%           6720-6722 Investment offices
%           6723-6723 Management investment, closed-end
%           6724-6724 Unit investment trusts                          
%           6725-6725 Face-amount certificate offices 
%           6726-6726 Unit inv trusts, closed-end                
%           6730-6733 Trusts
%           6740-6779 Investment offices
%           6790-6791 Miscellaneous investing
%           6792-6792 Oil royalty traders
%           6793-6793 Commodity traders                               
%           6794-6794 Patent owners & lessors
%           6795-6795 Mineral royalty traders
%           6798-6798 REIT
%           6799-6799 Investors, NEC

indus = indus + 48*(SIC >= 6200 & SIC <= 6299);
indus = indus + 48*(SIC == 6700);
indus = indus + 48*(SIC >= 6710 & SIC <= 6726);
indus = indus + 48*(SIC >= 6730 & SIC <= 6733);
indus = indus + 48*(SIC >= 6740 & SIC <= 6779);
indus = indus + 48*(SIC >= 6790 & SIC <= 6795);
indus = indus + 48*(SIC >= 6798 & SIC <= 6799);

% 49 Other  Almost Nothing
%           4950-4959 Sanitary services
%           4960-4961 Steam, air conditioning supplies
%           4970-4971 Irrigation systems
%           4990-4991 Cogeneration - SM power producer

indus = indus + 49*(SIC >= 4950 & SIC <= 4959);
indus = indus + 49*(SIC >= 4960 & SIC <= 4961);
indus = indus + 49*(SIC >= 4970 & SIC <= 4971);
indus = indus + 49*(SIC >= 4990 & SIC <= 4991);

% Store the FF10 industries an their names
FF49 = indus;
FF49Names = [{1},  {'Agric'}, {'Agriculture'}; ...
             {2},  {'Food'},  {'Food Products'}; ...
             {3},  {'Soda'},  {'Candy & Soda'}; ...
             {4},  {'Beer'},  {'Beer & Liquor'}; ...
             {5},  {'Smoke'}, {'Tobacco Products'}; ...
             {6},  {'Toys'},  {'Recreation'}; ...
             {7},  {'Fun'},   {'Entertainment'}; ...
             {8},  {'Books'}, {'Printingand Publishing'}; ...
             {9},  {'Hshld'}, {'ConsumerGoods'}; ...
             {10}, {'Clths'}, {'Apparel'}; ...
             {11}, {'Hlth'},  {'Healthcare'}; ...
             {12}, {'MedEq'}, {'Medical Equipment'}; ...
             {13}, {'Drugs'}, {'Pharmaceutical Products'}; ...
             {14}, {'Chems'}, {'Chemicals'}; ...
             {15}, {'Rubbr'}, {'Rubber and Plastic Products'}; ...
             {16}, {'Txtls'}, {'Textiles'}; ...
             {17}, {'BldMt'}, {'Construction Materials'}; ...
             {18}, {'Cnstr'}, {'Construction'}; ...
             {19}, {'Steel'}, {'Steel Works Etc'}; ...
             {20}, {'FabPr'}, {'Fabricated Products'}; ...
             {21}, {'Mach'},  {'Machinery'}; ...
             {22}, {'ElcEq'}, {'Electrical Equipment'}; ...
             {23}, {'Autos'}, {'Automobiles and Trucks'}; ...
             {24}, {'Aero'},  {'Aircraft'}; ...
             {25}, {'Ships'}, {'Shipbuilding, Railroad Equipment'}; ...
             {26}, {'Guns'},  {'Defense'}; ...
             {27}, {'Gold'},  {'PreciousMetals'}; ...
             {28}, {'Mines'}, {'Non-Metallic and Industrial Metal Mining'}; ...
             {29}, {'Coal'},  {'Coal'}; ...
             {30}, {'Oil'},   {'Petroleumand Natural Gas'}; ...
             {31}, {'Util'},  {'Utilities'}; ...
             {32}, {'Telcm'}, {'Communication'}; ...
             {33}, {'PerSv'}, {'PersonalServices'}; ...
             {34}, {'BusSv'}, {'BusinessServices'}; ...
             {35}, {'Hardw'}, {'Computers'}; ...
             {36}, {'Softw'}, {'ComputerSoftware'}; ...
             {37}, {'Chips'}, {'Electronic Equipment'}; ...
             {38}, {'LabEq'}, {'Measuringand Control Equipment'}; ...
             {39}, {'Paper'}, {'BusinessSupplies'}; ...
             {40}, {'Boxes'}, {'ShippingContainers'}; ...
             {41}, {'Trans'}, {'Transportation'}; ...
             {42}, {'Whlsl'}, {'Wholesale'}; ...
             {43}, {'Rtail'}, {'Retail'}; ...
             {44}, {'Meals'}, {'Restaurants, Hotels, Motels'}; ...
             {45}, {'Banks'}, {'Banking'}; ...
             {46}, {'Insur'}, {'Insurance'}; ...
             {47}, {'RlEst'}, {'Real Estate'}; ...
             {48}, {'Fin'},   {'Trading'}; ...
             {49}, {'Other'}, {'Almost Nothing'};];
FF49Names = array2table(FF49Names, 'VariableNames', {'number','shortName','longName'});


