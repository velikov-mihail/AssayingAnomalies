% PURPOSE: An example using angleplotmap
%  The x-axis contains the angle in radians between the vector joining a couple of sites and the x-axis
%  The y-axis contains the absolute difference of the variable between these two sites
%---------------------------------------------------
% USAGE: angleplotmap_d
%---------------------------------------------------

clear all;
% A spatial dataset on crime, household income and housing values
% in 49 Columbus, Ohio neighborhoods
% from:
% Anselin, L. 1988. Spatial Econometrics: Methods and Models,
% (Dorddrecht: Kluwer Academic Publishers).

% 5 columns:
% column1 = crime
% column2 = household income
% column3 = house values
% column4 = latitude coordinate
% column5 = longitude coordinate

% load Anselin (1988) Columbus neighborhood crime data
load anselin2.data;
crime = anselin2(:,1);
latt = anselin2(:,4);
long = anselin2(:,5);

crime = roundoff(crime,0);

load columbus.poly; % see the file for polygon format
carte = columbus;
opt = 2;

angleplotmap(latt,long,crime,opt,[],carte);