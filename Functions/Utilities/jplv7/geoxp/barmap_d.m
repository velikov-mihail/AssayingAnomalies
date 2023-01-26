% PURPOSE: An example using barmap
%          to examine the scatter of a
%          variable using a map
%---------------------------------------------------
% USAGE: barmap_d
%---------------------------------------------------

clear all;
% A spatial dataset on crime, household income and housing values
% in 49 Columbus, Ohio neighborhoods
% from:
% Anselin, L. 1988. Spatial Econometrics: Methods and Models,
% (Dorddrecht: Kluwer Academic Publishers).

filename = 'columbus';

[results,poly] = shpfile_read(filename);

% results.data contains 49 rows, 22 columns, see results.vnames
% col 1 = AREA      
% col 2 = PERIMETER 
% col 3 = COLUMBUS_ 
% col 4 = COLUMBUS_I
% col 5 = POLYID    
% col 6 = NEIG      
% col 7 = HOVAL     
% col 8 = INC       
% col 9 = CRIME     
% col 10 = OPEN      
% col 12 = PLUMB     
% col 12 = DISCBD    
% col 13 = X         
% col 14 = Y         
% col 15 = AREA      
% col 16 = NSA       
% col 17 = NSB       
% col 18 = EW        
% col 19 = CP        
% col 20 = THOUS     
% col 21 = NEIGNO    
% col 22 = PERIM     

% pull out crime
crime = results.data(:,9);
% pull out latt-long
long = results.data(:,13);
latt = results.data(:,14);

barmap(latt,long,crime);