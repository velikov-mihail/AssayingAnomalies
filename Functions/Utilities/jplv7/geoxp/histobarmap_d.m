% PURPOSE: An example using histobarmap
%          to examine the scatter of a
%          variable using a map
%---------------------------------------------------
% USAGE: histobarmap_d
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
load anselin2.data;
crime = anselin2(:,1);
housev = anselin2(:,3);
latt = anselin2(:,4);
long = anselin2(:,5);
n = length(latt);
crime = roundoff(crime,0);
housev = roundoff(housev,0);

load columbus.poly; % see the file for polygon format
carte = columbus;
nclasses = 5;
histobarmap(latt,long,crime,housev,nclasses,carte,[],1);