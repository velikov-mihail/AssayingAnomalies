function [FF10, FF10Names] = makeFF10Indus(SIC) 
% PURPOSE: This function creates a Fama and French 10-industry
% classification index and a table with the industry names
%------------------------------------------------------------------------------------------
% USAGE:   
% [FF10, FF10Names] = makeFF49Indus(SIC)          
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -SIC - a matrix containing SIC codes
%------------------------------------------------------------------------------------------
% Output:
%        -inds - matrix with the industries indicators
%        -FF10Names - table with the industry names
%------------------------------------------------------------------------------------------
% Examples:
%
% [FF10, FF10Names] = makeFF49Indus(SIC)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% 1 NoDur  Consumer NonDurables -- Food, Tobacco, Textiles, Apparel, Leather, Toys
indus = (SIC >= 100 & SIC <= 999);
indus = indus + (SIC >= 2000 & SIC <= 2399);
indus = indus + (SIC >= 2700 & SIC <= 2749);
indus = indus + (SIC >= 2770 & SIC <= 2799);
indus = indus + (SIC >= 3100 & SIC <= 3199);
indus = indus + (SIC >= 3940 & SIC <= 3989);

%  2 Durbl  Consumer Durables -- Cars, TV's, Furniture, Household Appliances
indus = indus + 2*(SIC >=2500 &  SIC <= 2519);
indus = indus + 2*(SIC >=2590 &  SIC <= 2599);
indus = indus + 2*(SIC >=3630 &  SIC <= 3659);
indus = indus + 2*(SIC >=3710 &  SIC <= 3711);
indus = indus + 2*(SIC >=3714 &  SIC <= 3714);
indus = indus + 2*(SIC >=3716 &  SIC <= 3716);
indus = indus + 2*(SIC >=3750 &  SIC <= 3751);
indus = indus + 2*(SIC >=3792 &  SIC <= 3792);
indus = indus + 2*(SIC >=3900 &  SIC <= 3939);
indus = indus + 2*(SIC >=3990 &  SIC <= 3999);

%  3 Manuf  Manufacturing -- Machinery, Trucks, Planes, Chemicals, Off Furn, Paper, Com Printing
indus = indus + 3*(SIC >=2520 &  SIC <= 2589);
indus = indus + 3*(SIC >=2600 &  SIC <= 2699);
indus = indus + 3*(SIC >=2750 &  SIC <= 2769);
indus = indus + 3*(SIC >=2800 &  SIC <= 2829);
indus = indus + 3*(SIC >=2840 &  SIC <= 2899);
indus = indus + 3*(SIC >=3000 &  SIC <= 3099);
indus = indus + 3*(SIC >=3200 &  SIC <= 3569);
indus = indus + 3*(SIC >=3580 &  SIC <= 3621);
indus = indus + 3*(SIC >=3623 &  SIC <= 3629);
indus = indus + 3*(SIC >=3700 &  SIC <= 3709);
indus = indus + 3*(SIC >=3712 &  SIC <= 3713);
indus = indus + 3*(SIC >=3715 &  SIC <= 3715);
indus = indus + 3*(SIC >=3717 &  SIC <= 3749);
indus = indus + 3*(SIC >=3752 &  SIC <= 3791);
indus = indus + 3*(SIC >=3793 &  SIC <= 3799);
indus = indus + 3*(SIC >=3860 &  SIC <= 3899);

%  4 Enrgy  Oil, Gas, and Coal Extraction and Products
indus = indus + 4*(SIC >=1200 &  SIC <= 1399);
indus = indus + 4*(SIC >=2900 &  SIC <= 2999);

%  5 HiTec  Business Equipment -- Computers, Software, and Electronic Equipment
indus = indus + 5*(SIC >=3570 &  SIC <= 3579);
indus = indus + 5*(SIC >=3622 &  SIC <= 3622);% Industrial controls
indus = indus + 5*(SIC >=3660 &  SIC <= 3692);
indus = indus + 5*(SIC >=3694 &  SIC <= 3699);
indus = indus + 5*(SIC >=3810 &  SIC <= 3839);
indus = indus + 5*(SIC >=7370 &  SIC <= 7372);% Services - computer programming and data processing
indus = indus + 5*(SIC >=7373 &  SIC <= 7373);% Computer integrated systems design
indus = indus + 5*(SIC >=7374 &  SIC <= 7374);% Services - computer processing, data prep
indus = indus + 5*(SIC >=7375 &  SIC <= 7375);% Services - information retrieval services
indus = indus + 5*(SIC >=7376 &  SIC <= 7376);% Services - computer facilities management service
indus = indus + 5*(SIC >=7377 &  SIC <= 7377);% Services - computer rental and leasing
indus = indus + 5*(SIC >=7378 &  SIC <= 7378);% Services - computer maintanence and repair
indus = indus + 5*(SIC >=7379 &  SIC <= 7379);% Services - computer related services
indus = indus + 5*(SIC >=7391 &  SIC <= 7391);% Services - R&D labs
indus = indus + 5*(SIC >=8730 &  SIC <= 8734);% Services - research, development, testing labs

%  6 Telcm  Telephone and Television Transmission
indus = indus + 6*(SIC >=4800 &  SIC <= 4899);

%  7 Shops  Wholesale, Retail, and Some Services (Laundries, Repair Shops)
indus = indus + 7*(SIC >=5000 &  SIC <= 5999);
indus = indus + 7*(SIC >=7200 &  SIC <= 7299);
indus = indus + 7*(SIC >=7600 &  SIC <= 7699);

%  8 Hlth   Healthcare, Medical Equipment, and Drugs
indus = indus + 8*(SIC >=2830 &  SIC <= 2839);
indus = indus + 8*(SIC >=3693 &  SIC <= 3693);
indus = indus + 8*(SIC >=3840 &  SIC <= 3859);
indus = indus + 8*(SIC >=8000 &  SIC <= 8099);

%  9 Utils  Utilities
indus = indus + 9*(SIC >=4900 &  SIC <= 4949);

% 10 Other  Other -- Mines, Constr, BldMt, Trans, Hotels, Bus Serv, Entertainment, Finance
indus((SIC)>0 & (indus==0)) = 10;

% Store the FF10 industries an their names
FF10 = indus;
FF10Names = [{1},  {'NoDur'}, {'Consumer NonDurables'};                       ...
             {2},  {'Durbl'}, {'Consumer Durables'};                          ...
             {3},  {'Manuf'}, {'Manufacturing'};                              ...
             {4},  {'Enrgy'}, {'Oil, Gas, and Coal Extraction and Products'}; ...
             {5},  {'HiTec'}, {'Business Equipment'};                         ...
             {6},  {'Telcm'}, {'Telephone and Television Transmission'};      ...
             {7},  {'Shops'}, {'Wholesale, Retail, and Some Services'};       ...
             {8},  {'Hlth'},  {'Healthcare, Medical Equipment, and Drugs'};   ...
             {9},  {'Utils'}, {'Utilities'};                                  ...
             {10}, {'Other'}, {'Other'};];
FF10Names = array2table(FF10Names, 'VariableNames', {'number','shortName','longName'});



